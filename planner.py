"""Runner script for the GeminiPlanner factory seat."""

import argparse
import asyncio
import logging
from dotenv import load_dotenv
from band import configure_logging

from factory.adapter import run_factory_agent
from factory.config import SEAT_CONFIGS

logger = logging.getLogger(__name__)


def main() -> None:
    seat_cfg = SEAT_CONFIGS["planner"]
    parser = argparse.ArgumentParser(description=f"Run the {seat_cfg.role} factory seat")
    parser.add_argument(
        "--model", "-m",
        default=seat_cfg.default_model,
        help=f"Gemini model ID to run (default: {seat_cfg.default_model}).",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow dynamic model fallback if primary model errors (use only during development).",
    )
    args = parser.parse_args()

    load_dotenv()
    configure_logging(root_level="INFO")

    asyncio.run(
        run_factory_agent(
            seat_config=seat_cfg,
            requested_model=args.model,
            allow_fallback=args.allow_fallback,
        )
    )


if __name__ == "__main__":
    main()