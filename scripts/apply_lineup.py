"""Make the Band Desktop seats of a lineup match their mandates.

For every Claude Code seat in the lineup this:
  1. sets the seat's Band owner instructions to its rendered mandate, and
  2. pins the model on the seat's parked runtime template to the mandate's `Model:`.

Google ADK seats need nothing here: `factory-seat` loads the mandate and model itself.

    python scripts/apply_lineup.py --lineup claude --mandates ../band-work/toy-result/mandates
    python scripts/apply_lineup.py --lineup hybrid --dry-run

Requires the `band` CLI and a running Band daemon. Changes only the seats in the lineup.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factory.lineup import CLAUDE_CODE, ROLES, ROOT, load_lineup  # noqa: E402


def run(cmd: list[str], dry: bool) -> str:
    print("$", " ".join(cmd))
    if dry:
        return ""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SystemExit(f"failed ({res.returncode}): {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def template_id(band_as: str) -> str:
    out = subprocess.run(["band", "runtime", "template", "show", "--as", band_as],
                         capture_output=True, text=True, check=True).stdout
    match = re.search(r"^template (\S+)", out, re.M)
    if not match:
        raise SystemExit(f"could not read the runtime template of {band_as}:\n{out}")
    return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lineup", required=True)
    parser.add_argument("--mandates", default=str(ROOT / "mandates"),
                        help="folder holding the rendered mandates (default: this repo's mandates/)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lineup = load_lineup(args.lineup)
    for role in ROLES:
        seat = lineup.seat(role)
        if seat.harness != CLAUDE_CODE:
            print(f"# {role}: {seat.name} runs on {seat.harness}; start it with "
                  f"`factory-seat --role {role} --lineup {lineup.name}`")
            continue
        mandate = Path(args.mandates) / seat.mandate_file
        if not mandate.is_file():
            raise SystemExit(f"{mandate} is missing; run scripts/render_mandates.py first")
        if not seat.band_as:
            raise SystemExit(f"{role} seat {seat.name} has no band_as in lineups.toml")
        run(["band", "agent", "instructions", "set", "--as", seat.band_as,
             "--instructions-file", str(mandate.resolve())], args.dry_run)
        host = "<template>" if args.dry_run else template_id(seat.band_as)
        run(["band", "runtime", "template", "set", "--as", seat.band_as,
             "--host-session", host, "--runtime-model", seat.model], args.dry_run)


if __name__ == "__main__":
    main()
