"""CLI entrypoint for the GeminiBuilder factory seat."""

from __future__ import annotations

import argparse
import asyncio
import logging

from dotenv import load_dotenv
from band import configure_logging

from factory.adapter import run_factory_agent
from factory.config import SEAT_CONFIGS

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    seat_cfg = SEAT_CONFIGS["builder"]
    parser = argparse.ArgumentParser(
        description=f"Run the {seat_cfg.role} factory seat (Dark Factory)",
    )
    parser.add_argument(
        "--model", "-m",
        default=seat_cfg.default_model,
        help=f"Gemini model ID to run (default: {seat_cfg.default_model}).",
    )
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow dynamic model fallback (development only; disabled by default to preserve mandate compliance).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    load_dotenv()
    configure_logging(root_level="INFO")

    seat_cfg = SEAT_CONFIGS["builder"]
    asyncio.run(
        run_factory_agent(
            seat_config=seat_cfg,
            requested_model=args.model,
            allow_fallback=args.allow_fallback,
        )
    )


if __name__ == "__main__":
    main()
