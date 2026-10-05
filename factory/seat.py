"""Run one Google ADK seat of a lineup.

    factory-seat --lineup hybrid --role coordinator
    factory-seat --lineup gemini --role implementer --workspace /abs/path/band-work

The seat's instructions are its rendered mandate (mandates/<seat>.md by default), so the
text a judge reads is exactly the text the seat runs. The model is the mandate's `Model:`
line; it is verified against the Gemini API before connecting.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

from factory.lineup import GOOGLE_ADK, ROLES, ROOT, load_lineup

logger = logging.getLogger(__name__)


def build_parser(default_role: str | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lineup", default=os.getenv("FACTORY_LINEUP", "hybrid"),
                        help="lineup in factory/lineups.toml (default: $FACTORY_LINEUP or hybrid)")
    parser.add_argument("--role", choices=ROLES, default=default_role, required=default_role is None)
    parser.add_argument("--mandates", default=str(ROOT / "mandates"),
                        help="folder of rendered mandates (default: this repo's mandates/)")
    parser.add_argument("--workspace", default=os.getenv("FACTORY_WORKSPACE"),
                        help="absolute root the workspace tools may touch (default: $FACTORY_WORKSPACE)")
    parser.add_argument("--model", "-m", help="override the mandate's model (needs --allow-fallback)")
    parser.add_argument("--allow-fallback", action="store_true",
                        help="development only: allow a model other than the mandate's")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="do not verify the model against the Gemini API before connecting")
    return parser


def declared_model(mandate_text: str) -> str:
    match = re.search(r"(?im)^\s*Model\s*:\s*(\S+)", mandate_text)
    if not match:
        raise SystemExit("the mandate has no `Model:` line")
    return match.group(1)


def main(default_role: str | None = None) -> None:
    args = build_parser(default_role).parse_args()
    load_dotenv()
    from band import configure_logging

    configure_logging(root_level=os.getenv("FACTORY_LOG_LEVEL", "INFO"))

    lineup = load_lineup(args.lineup)
    seat = lineup.seat(args.role)
    if seat.harness != GOOGLE_ADK:
        raise SystemExit(
            f"In lineup {lineup.name!r} the {args.role} is {seat.name!r} on {seat.harness}: "
            "Band Desktop runs that seat, not this script (see scripts/apply_lineup.py).")
    if not seat.agent_entry:
        raise SystemExit(f"{seat.name} has no agent_entry in factory/lineups.toml")

    mandate_path = Path(args.mandates) / seat.mandate_file
    if not mandate_path.is_file():
        raise SystemExit(f"{mandate_path} is missing; run scripts/render_mandates.py --lineup {lineup.name}")
    mandate_text = mandate_path.read_text(encoding="utf-8")
    declared = declared_model(mandate_text)
    if declared != seat.model:
        raise SystemExit(f"{mandate_path} declares {declared} but lineups.toml says {seat.model}; re-render")

    from factory.adapter import choose_model, run_seat
    from factory.workspace_tools import TOOLS_BY_ROLE

    tools = []
    if args.workspace:
        os.environ["FACTORY_WORKSPACE"] = str(Path(args.workspace).expanduser().resolve())
        tools = TOOLS_BY_ROLE[args.role]
    elif args.role != "coordinator":
        raise SystemExit(f"the {args.role} must change files and run checks: pass --workspace "
                         "or set FACTORY_WORKSPACE")

    model = choose_model(declared, args.model, args.allow_fallback, args.skip_preflight)
    logger.info("Starting %s as %s (%s) on %s", seat.name, args.role, lineup.name, model)
    asyncio.run(run_seat(agent_key=seat.agent_entry, model=model,
                         mandate_text=mandate_text, tools=tools))


if __name__ == "__main__":
    main()
