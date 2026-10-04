import argparse
import asyncio
import logging
import os
from dotenv import load_dotenv
from band import Agent, configure_logging
from band.adapters import GoogleADKAdapter
from band.adapters.google_adk import GoogleADKAdapterConfig
from band.config import load_agent_config

logger = logging.getLogger(__name__)

# Models in preference order — fallback tries the next one on 404
MODEL_FALLBACKS = [
    "gemini-3.8-flash",
    "gemini-3.8-pro",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]


def build_adapter(model: str) -> GoogleADKAdapter:
    """Create a GoogleADKAdapter with the given model name."""
    config = GoogleADKAdapterConfig(
        model=model,
        custom_section="""
        You are a skilled software engineer.
        When given a task, write clean, correct code.
        Always respond clearly and use the band_send_message tool when needed.
        """,
    )
    return GoogleADKAdapter(config=config)


async def main():
    parser = argparse.ArgumentParser(description="Run the GeminiBuilder agent")
    parser.add_argument(
        "--model", "-m",
        default=MODEL_FALLBACKS[0],
        help=f"Gemini model to use (default: {MODEL_FALLBACKS[0]}). "
             f"Available: {', '.join(MODEL_FALLBACKS)}",
    )
    args = parser.parse_args()

    load_dotenv()
    configure_logging(root_level="INFO")

    # Load credentials
    agent_id, api_key = load_agent_config("gemini_builder")

    # Build fallback order: chosen model first, then the rest
    models_to_try = [args.model] + [m for m in MODEL_FALLBACKS if m != args.model]

    adapter = None
    for model in models_to_try:
        logger.info("Trying model: %s", model)
        try:
            adapter = build_adapter(model)
            agent = Agent.create(
                adapter=adapter,
                agent_id=agent_id,
                api_key=api_key,
                ws_url=os.getenv("BAND_WS_URL"),
                rest_url=os.getenv("BAND_REST_URL"),
            )
            logger.info("Gemini agent is running with model '%s'! Press Ctrl+C to stop.", model)
            await agent.run()
            break  # Clean exit
        except Exception as e:
            error_str = str(e)
            if "404" in error_str and "no longer available" in error_str.lower():
                logger.warning("Model '%s' is unavailable, trying next fallback...", model)
                continue
            else:
                raise
    else:
        logger.error("All models exhausted. None of %s are available.", models_to_try)
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())