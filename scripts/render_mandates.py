"""Write one mandate per seat of a lineup into a mandates/ folder.

    python scripts/render_mandates.py --lineup hybrid                 # this repo's mandates/
    python scripts/render_mandates.py --lineup claude --out ../band-work/toy-result/mandates

Existing *.md files in the output folder are removed first, so the folder holds exactly
the mandates of the seats in the lineup (gate 1 checks every seat in the room has one, and
a mandate for a seat nobody configured only confuses a judge).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factory.lineup import ROLES, ROOT, load_lineup, render_mandate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lineup", required=True)
    parser.add_argument("--out", default=str(ROOT / "mandates"))
    args = parser.parse_args()

    lineup = load_lineup(args.lineup)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.md"):
        old.unlink()
    for role in ROLES:
        seat = lineup.seat(role)
        (out / seat.mandate_file).write_text(render_mandate(lineup, role), encoding="utf-8")
        print(f"{role:12} -> {out / seat.mandate_file}  ({seat.harness}, {seat.model})")


if __name__ == "__main__":
    main()
