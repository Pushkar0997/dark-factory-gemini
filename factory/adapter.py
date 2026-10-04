"""Google ADK Adapter creation and resilient agent runtime management."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid
from typing import Any, Sequence

from band import Agent
from band.adapters.google_adk import (
    GoogleADKAdapter,
    GoogleADKAdapterConfig,
    _require_adk,
    _APP_NAME,
)
from band.config import load_agent_config
from band.converters.google_adk import GoogleADKMessages
from band.core.protocols import GENERIC_PROVIDER_FAILURE_MESSAGE, AgentToolsProtocol
from band.core.types import Emit, PlatformMessage, TurnUsage
from band_sdk_core import AgentFailure

from factory.config import FactorySeatConfig, MODEL_CANDIDATES

logger = logging.getLogger(__name__)


def is_transient_error(exc: Exception) -> bool:
    """Determine whether an exception represents a rate limit or transient service error."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 500, 502, 503, 504):
        return True

    exc_str = str(exc).lower()
    transient_indicators = (
        "429",
        "resource_exhausted",
        "resourceexhausted",
        "rate limit",
        "ratelimit",
        "quota",
        "503",
        "unavailable",
        "service unavailable",
        "overloaded",
        "deadline exceeded",
        "deadlineexceeded",
        "timeout",
        "timed out",
        "connection reset",
        "temporary failure",
    )
    return any(indicator in exc_str for indicator in transient_indicators)


class ResilientGoogleADKAdapter(GoogleADKAdapter):
    """Google ADK Adapter with rate-limit pacing, exponential backoff, and retry handling.

    Guarantees:
    - Strictly preserves the declared model identity across all retry attempts.
    - Absorbs transient 429 (ResourceExhausted) and 503 errors without dropping Band turns.
    - Implements inter-turn pacing to avoid burst rate-limit triggers on free tier quotas.
    """

    def __init__(
        self,
        config: GoogleADKAdapterConfig,
        max_retries: int | None = None,
        initial_backoff: float | None = None,
        backoff_factor: float = 2.0,
        max_backoff: float | None = None,
        turn_delay: float | None = None,
        jitter_max: float = 2.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(config=config, **kwargs)
        self.max_retries = max_retries or int(os.getenv("FACTORY_MAX_RETRIES", "5"))
        self.initial_backoff = initial_backoff or float(os.getenv("FACTORY_INITIAL_BACKOFF", "4.0"))
        self.backoff_factor = backoff_factor
        self.max_backoff = max_backoff or float(os.getenv("FACTORY_MAX_BACKOFF", "60.0"))
        self.turn_delay = turn_delay or float(os.getenv("FACTORY_TURN_DELAY", "1.5"))
        self.jitter_max = jitter_max
        self._last_turn_completed_at: float = 0.0

    async def on_message(
        self,
        msg: PlatformMessage,
        tools: AgentToolsProtocol,
        history: GoogleADKMessages,
        participants_msg: str | None,
        contacts_msg: str | None,
        *,
        is_session_bootstrap: bool,
        room_id: str,
    ) -> None:
        """Handle incoming message with inter-turn pacing and transient backoff retries."""
        _, _, _, types = _require_adk()

        logger.debug("Handling message %s in room %s", msg.id, room_id)

        # 1. Inter-turn pacing: throttle burst API calls across consecutive turns
        if self.turn_delay > 0 and self._last_turn_completed_at > 0:
            elapsed = time.monotonic() - self._last_turn_completed_at
            if elapsed < self.turn_delay:
                wait_time = self.turn_delay - elapsed
                logger.debug(
                    "Room %s [%s]: Pacing throttle sleeping for %.2fs",
                    room_id,
                    self.agent_name,
                    wait_time,
                )
                await asyncio.sleep(wait_time)

        # 2. Seed or maintain room history
        if is_session_bootstrap:
            self._room_history[room_id] = list(history) if history else []
            if history:
                logger.info(
                    "Room %s: Loaded %s historical messages",
                    room_id,
                    len(history),
                )
        elif room_id not in self._room_history:
            self._room_history[room_id] = []

        # 3. Construct user message content with windowed transcript
        parts: list[str] = []
        room_history = self._room_history[room_id]
        if room_history:
            windowed = room_history[-self.config.max_history_messages :]
            transcript = self._format_history_transcript(windowed)
            if transcript:
                if len(transcript) > self.config.max_transcript_chars:
                    original_len = len(transcript)
                    transcript = transcript[-self.config.max_transcript_chars :]
                    nl = transcript.find("\n")
                    if nl != -1:
                        transcript = transcript[nl + 1 :]
                    logger.warning(
                        "Room %s: Transcript truncated from %d to %d chars to stay within token budget",
                        room_id,
                        original_len,
                        len(transcript),
                    )
                parts.append(
                    f"[Previous conversation context]\n{transcript}\n"
                    f"[End of previous context]\n\n"
                )

        if participants_msg:
            parts.append(f"[System]: {participants_msg}")
            logger.info("Room %s: Participants updated", room_id)

        if contacts_msg:
            parts.append(f"[System]: {contacts_msg}")
            logger.info("Room %s: Contacts broadcast received", room_id)

        parts.append(msg.format_for_llm())
        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text="\n".join(parts))],
        )

        logger.info(
            "Room %s: Running resilient ADK agent (seat='%s', model='%s', max_retries=%d, bootstrap=%s, history_size=%s)",
            room_id,
            self.agent_name,
            self.config.model,
            self.max_retries,
            is_session_bootstrap,
            len(room_history),
        )

        # 4. Turn execution with retry and exponential backoff
        for attempt in range(1, self.max_retries + 1):
            runner: Any = None
            turn_usage = TurnUsage()
            final_response_text = ""
            try:
                runner = self._create_runner(tools)
                session_id = str(uuid.uuid4())
                self._room_sessions[room_id] = session_id
                await runner.session_service.create_session(
                    app_name=_APP_NAME,
                    user_id=room_id,
                    session_id=session_id,
                )

                async for event in runner.run_async(
                    user_id=room_id,
                    session_id=session_id,
                    new_message=user_content,
                ):
                    if Emit.USAGE in self.features.emit:
                        turn_usage = turn_usage + self._usage_from_event(event)

                    if Emit.TOOL_CALLS in self.features.emit:
                        try:
                            await self._report_event(event, tools)
                        except Exception as e:
                            logger.warning("Failed to report event: %s", e)

                    if event.is_final_response():
                        final_response_text = self._extract_event_text(event)
                        logger.debug("Room %s: ADK agent completed with final response", room_id)

                # Successful turn completion
                self._last_turn_completed_at = time.monotonic()
                self._room_history[room_id].append(
                    {"role": "user", "content": msg.format_for_llm()}
                )
                if final_response_text:
                    self._room_history[room_id].append(
                        {"role": "model", "content": final_response_text}
                    )

                trim_threshold = self.config.max_history_messages * 2
                if len(self._room_history[room_id]) > trim_threshold:
                    self._room_history[room_id] = self._room_history[room_id][-self.config.max_history_messages :]

                return

            except Exception as exc:
                if is_transient_error(exc) and attempt < self.max_retries:
                    delay = min(
                        self.max_backoff,
                        self.initial_backoff * (self.backoff_factor ** (attempt - 1)),
                    ) + random.uniform(0.5, self.jitter_max)
                    logger.warning(
                        "Room %s [%s]: Transient error / rate limit (429/503) encountered on model '%s' (%s). "
                        "Preserving declared model identity. Retrying in %.2fs (attempt %d/%d)...",
                        room_id,
                        self.agent_name,
                        self.config.model,
                        exc,
                        delay,
                        attempt,
                        self.max_retries,
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.exception(
                        "Error running ADK agent in room %s (attempt %d/%d exhausted, model='%s')",
                        room_id,
                        attempt,
                        self.max_retries,
                        self.config.model,
                    )
                    await tools.send_failure(
                        AgentFailure("google_adk", GENERIC_PROVIDER_FAILURE_MESSAGE)
                    )
                    raise
            finally:
                try:
                    await self.emit_usage(tools, turn_usage)
                finally:
                    if runner is not None:
                        await runner.close()


def build_adapter(model: str, custom_section: str) -> ResilientGoogleADKAdapter:
    """Instantiate a ResilientGoogleADKAdapter with explicit model and instructions."""
    config = GoogleADKAdapterConfig(
        model=model,
        custom_section=custom_section,
    )
    return ResilientGoogleADKAdapter(config=config)


async def run_factory_agent(
    seat_config: FactorySeatConfig,
    requested_model: str | None = None,
    allow_fallback: bool = False,
    candidate_models: Sequence[str] = MODEL_CANDIDATES,
) -> None:
    """Run an individual factory seat with verified configuration and model handling.

    Default mode: Strict single-model execution (mandate compliance).
    Development mode (--allow-fallback): Allows candidate model trial on initial startup failures.
    """
    agent_id, api_key = load_agent_config(seat_config.config_key)
    ws_url = os.getenv("BAND_WS_URL")
    rest_url = os.getenv("BAND_REST_URL")

    primary_model = requested_model or seat_config.default_model

    if not allow_fallback:
        models_to_try = [primary_model]
    else:
        models_to_try = [primary_model] + [m for m in candidate_models if m != primary_model]

    for model in models_to_try:
        logger.info(
            "Starting %s seat with model '%s' (strict=%s)...",
            seat_config.role,
            model,
            not allow_fallback,
        )
        try:
            adapter = build_adapter(model=model, custom_section=seat_config.system_prompt)
            agent = Agent.create(
                adapter=adapter,
                agent_id=agent_id,
                api_key=api_key,
                ws_url=ws_url,
                rest_url=rest_url,
            )
            logger.info("Factory seat %s is running with model '%s'.", seat_config.role, model)
            await agent.run()
            break
        except Exception as exc:
            error_str = str(exc)
            if allow_fallback and any(err in error_str for err in ("404", "503", "UNAVAILABLE")):
                logger.warning(
                    "Model '%s' failed for %s (%s). Attempting next candidate...",
                    model,
                    seat_config.role,
                    exc,
                )
                continue
            logger.error("Seat %s encountered fatal error: %s", seat_config.role, exc)
            raise
    else:
        logger.critical("All candidate models exhausted for %s.", seat_config.role)
        raise SystemExit(1)
