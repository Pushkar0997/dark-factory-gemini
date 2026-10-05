"""Google ADK seat runtime: a rate-limit-resilient adapter and the seat launcher."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
import uuid
from typing import Any

from band import Agent
from band.adapters.google_adk import (
    GoogleADKAdapter,
    GoogleADKAdapterConfig,
    _APP_NAME,
    _require_adk,
)
from band.config import load_agent_config
from band.converters.google_adk import GoogleADKMessages
from band.core.protocols import GENERIC_PROVIDER_FAILURE_MESSAGE, AgentToolsProtocol
from band.core.types import Emit, PlatformMessage, TurnUsage
from band.runtime.custom_tools import CustomToolDef
from band_sdk_core import AgentFailure

from factory.config import MODEL_CANDIDATES, RetryPolicy

logger = logging.getLogger(__name__)

_TRANSIENT_CODES = {408, 429, 500, 502, 503, 504}
_PERMANENT_CODES = {400, 401, 403, 404}
_TRANSIENT_TEXT = (
    "resource_exhausted", "resourceexhausted", "rate limit", "ratelimit", "too many requests",
    "quota", "unavailable", "overloaded", "deadline exceeded", "deadlineexceeded",
    "timed out", "timeout", "connection reset", "connection aborted", "temporary failure",
    "internal error", "server disconnected",
)
_RETRY_AFTER = re.compile(r"(?i)retry(?:delay|[ _-]?in|[ _-]?after)?\W{0,4}(\d+(?:\.\d+)?)\s*s")


def _status_code(exc: BaseException) -> int | None:
    for attr in ("code", "status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    match = re.match(r"\s*(\d{3})\b", str(exc))
    return int(match.group(1)) if match else None


def is_transient_error(exc: BaseException) -> bool:
    """True for errors worth retrying: rate limits, overload, 5xx and network timeouts."""
    code = _status_code(exc)
    if code in _TRANSIENT_CODES:
        return True
    if code in _PERMANENT_CODES:
        return False
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _TRANSIENT_TEXT)


def retry_after_seconds(exc: BaseException) -> float | None:
    """The server's suggested wait, when the error carries one (Gemini sends `retryDelay`)."""
    match = _RETRY_AFTER.search(str(exc))
    return float(match.group(1)) if match else None


class ResilientGoogleADKAdapter(GoogleADKAdapter):
    """GoogleADKAdapter plus turn pacing, bounded retry with jittered backoff, and
    duplicate-safe resumption.

    - The model never changes between attempts: retries reuse ``config.model``.
    - A turn that already performed side effects (sent a message, wrote a file, ran a
      command) before failing is not replayed blindly. The next attempt is told exactly
      which tool calls already completed and asked to continue from there, so a 429 in the
      middle of a turn does not post the same handoff twice.
    - When every attempt fails, the failure is reported to the room (``send_failure``) and
      logged with the room id, seat and model; it is never swallowed.
    """

    def __init__(
        self,
        config: GoogleADKAdapterConfig,
        *,
        policy: RetryPolicy | None = None,
        additional_tools: list[CustomToolDef] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(config=config, additional_tools=additional_tools, **kwargs)
        self.policy = policy or RetryPolicy.from_env()
        self._last_turn_completed_at = 0.0

    async def _pace(self, room_id: str) -> None:
        if self.policy.turn_delay <= 0 or not self._last_turn_completed_at:
            return
        wait = self.policy.turn_delay - (time.monotonic() - self._last_turn_completed_at)
        if wait > 0:
            logger.debug("Room %s [%s]: pacing %.2fs", room_id, self.agent_name, wait)
            await asyncio.sleep(wait)

    def _turn_text(self, room_id: str, msg: PlatformMessage, participants_msg: str | None,
                   contacts_msg: str | None) -> str:
        parts: list[str] = []
        windowed = self._room_history[room_id][-self.config.max_history_messages:]
        transcript = self._format_history_transcript(windowed) if windowed else ""
        if transcript:
            if len(transcript) > self.config.max_transcript_chars:
                transcript = transcript[-self.config.max_transcript_chars:]
                transcript = transcript[transcript.find("\n") + 1:]
                logger.warning("Room %s: transcript truncated to %d chars", room_id, len(transcript))
            parts.append(f"[Previous conversation context]\n{transcript}\n[End of previous context]\n")
        if participants_msg:
            parts.append(f"[System]: {participants_msg}")
        if contacts_msg:
            parts.append(f"[System]: {contacts_msg}")
        parts.append(msg.format_for_llm())
        return "\n".join(parts)

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
        _, _, _, types = _require_adk()
        await self._pace(room_id)

        if is_session_bootstrap:
            self._room_history[room_id] = list(history) if history else []
        else:
            self._room_history.setdefault(room_id, [])

        base_text = self._turn_text(room_id, msg, participants_msg, contacts_msg)
        completed: list[str] = []   # tool calls that finished, across all attempts
        final_text = ""

        for attempt in range(1, self.policy.max_attempts + 1):
            text = base_text
            if completed:
                text += (
                    "\n\n[System]: Your previous attempt at this turn was interrupted by a "
                    "transient model error AFTER these tool calls had already completed: "
                    + "; ".join(completed)
                    + ". Do not repeat them (the messages were delivered and the files were "
                    "written). Continue from where you stopped."
                )
            content = types.Content(role="user", parts=[types.Part.from_text(text=text)])
            runner: Any = None
            usage = TurnUsage()
            try:
                runner = self._create_runner(tools)
                session_id = str(uuid.uuid4())
                self._room_sessions[room_id] = session_id
                await runner.session_service.create_session(
                    app_name=_APP_NAME, user_id=room_id, session_id=session_id)
                async for event in runner.run_async(
                        user_id=room_id, session_id=session_id, new_message=content):
                    if Emit.USAGE in self.features.emit:
                        usage = usage + self._usage_from_event(event)
                    if Emit.TOOL_CALLS in self.features.emit:
                        try:
                            await self._report_event(event, tools)
                        except Exception as exc:  # reporting must never break a turn
                            logger.warning("Failed to report event: %s", exc)
                    for response in event.get_function_responses() or []:
                        completed.append(_describe_call(response))
                    if event.is_final_response():
                        final_text = self._extract_event_text(event)
                break
            except Exception as exc:
                if attempt < self.policy.max_attempts and is_transient_error(exc):
                    delay = self.policy.delay_for(attempt, random.random(), retry_after_seconds(exc))
                    logger.warning(
                        "Room %s [%s]: transient error on model %s (%s: %s). Attempt %d/%d; "
                        "%d tool call(s) already done; retrying in %.1fs with the same model.",
                        room_id, self.agent_name, self.config.model, type(exc).__name__,
                        str(exc)[:300], attempt, self.policy.max_attempts, len(completed), delay)
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    "Room %s [%s]: turn FAILED on model %s after %d attempt(s): %s: %s",
                    room_id, self.agent_name, self.config.model, attempt,
                    type(exc).__name__, str(exc)[:500])
                await tools.send_failure(AgentFailure("google_adk", GENERIC_PROVIDER_FAILURE_MESSAGE))
                raise
            finally:
                try:
                    await self.emit_usage(tools, usage)
                finally:
                    if runner is not None:
                        await runner.close()

        self._last_turn_completed_at = time.monotonic()
        room_history = self._room_history[room_id]
        room_history.append({"role": "user", "content": msg.format_for_llm()})
        if final_text:
            room_history.append({"role": "model", "content": final_text})
        if len(room_history) > self.config.max_history_messages * 2:
            del room_history[:-self.config.max_history_messages]


def _describe_call(response: Any) -> str:
    name = getattr(response, "name", "tool")
    payload = str(getattr(response, "response", ""))[:120].replace("\n", " ")
    return f"{name} -> {payload}"


def preflight_model(model: str) -> None:
    """Fail fast if the Gemini API does not know `model` (or the key is missing/invalid)."""
    from google import genai

    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        raise SystemExit("GOOGLE_API_KEY is not set (put it in .env; see .env.example)")
    genai.Client().models.get(model=model)


def choose_model(declared: str, requested: str | None, allow_fallback: bool,
                 skip_preflight: bool = False) -> str:
    """The model to run. Strict by default: the mandate's model, verified to exist."""
    model = requested or declared
    if requested and requested != declared and not allow_fallback:
        raise SystemExit(
            f"--model {requested} differs from the mandate's `Model: {declared}`. The mandate "
            "must name the model the seat runs: change factory/lineups.toml and re-render the "
            "mandates, or pass --allow-fallback for a development run.")
    if skip_preflight:
        return model
    candidates = [model] + ([m for m in MODEL_CANDIDATES if m != model] if allow_fallback else [])
    for candidate in candidates:
        try:
            preflight_model(candidate)
        except SystemExit:
            raise
        except Exception as exc:
            logger.error("Model preflight failed for %s: %s", candidate, str(exc)[:300])
            continue
        if candidate != declared:
            logger.critical(
                "MODEL MISMATCH: running %s but the mandate declares %s. Do NOT submit a run "
                "made this way without re-rendering the mandates for %s.",
                candidate, declared, candidate)
        return candidate
    raise SystemExit(f"No usable model among {candidates}; see the errors above.")


async def run_seat(*, agent_key: str, model: str, mandate_text: str,
                   tools: list[CustomToolDef]) -> None:
    """Connect one seat to Band and serve it until stopped."""
    agent_id, api_key = load_agent_config(agent_key)
    adapter = ResilientGoogleADKAdapter(
        GoogleADKAdapterConfig(model=model, custom_section=mandate_text),
        additional_tools=tools,
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("BAND_WS_URL"),
        rest_url=os.getenv("BAND_REST_URL"),
    )
    logger.info("Seat %s connected with model %s and %d workspace tool(s); policy=%s",
                agent_key, model, len(tools), adapter.policy)
    await agent.run()
