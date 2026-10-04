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

MODEL_FALLBACKS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
]

BUILDER_PROMPT = """
You are the Builder of a software factory.
Your job is to:
- Implement features based on clear instructions from the Planner
- Write clean, correct, and maintainable code
- Follow the plan step by step
- Hand completed work to the Reviewer for checking
Always respond clearly and use the band_send_message tool.
"""

def build_adapter(model: str) -> GoogleADKAdapter:
    config = GoogleADKAdapterConfig(
        model=model,
        custom_section=BUILDER_PROMPT,
    )
    return GoogleADKAdapter(config=config)

async def main():
    parser = argparse.ArgumentParser(description="Run the GeminiBuilder agent")
    parser.add_argument("--model", "-m", default=MODEL_FALLBACKS[0])
    args = parser.parse_args()

    load_dotenv()
    configure_logging(root_level="INFO")

    agent_id, api_key = load_agent_config("gemini_builder")
    models_to_try = [args.model] + [m for m in MODEL_FALLBACKS if m != args.model]

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
            logger.info("GeminiBuilder is running with model '%s'! Press Ctrl+C to stop.", model)
            await agent.run()
            break
        except Exception as e:
            if "404" in str(e) or "503" in str(e) or "UNAVAILABLE" in str(e):
                logger.warning("Model '%s' unavailable, trying next...", model)
                continue
            raise
    else:
        logger.error("All models failed.")
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())