"""Google ADK Adapter creation and agent runtime management."""

from __future__ import annotations

import logging
import os
from typing import Sequence

from band import Agent
from band.adapters import GoogleADKAdapter
from band.adapters.google_adk import GoogleADKAdapterConfig
from band.config import load_agent_config

from factory.config import FactorySeatConfig, MODEL_CANDIDATES

logger = logging.getLogger(__name__)


def build_adapter(model: str, custom_section: str) -> GoogleADKAdapter:
    """Instantiate a GoogleADKAdapter with explicit model and instructions."""
    config = GoogleADKAdapterConfig(
        model=model,
        custom_section=custom_section,
    )
    return GoogleADKAdapter(config=config)


async def run_factory_agent(
    seat_config: FactorySeatConfig,
    requested_model: str | None = None,
    allow_fallback: bool = False,
    candidate_models: Sequence[str] = MODEL_CANDIDATES,
) -> None:
    """Run an individual factory seat with verified configuration and model handling."""
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
