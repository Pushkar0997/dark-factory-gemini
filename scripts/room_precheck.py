"""Preview gates 1 and 2 on a live room, before the manual room.json download.

    python scripts/room_precheck.py <room id> [--mandates mandates/]

Reads the room through `band room messages --json` (as the account owner) and applies the
same logic `harness check` applies to room.json: agent seats = senders of type Agent; gate 1
needs >= 3 of them, each with mandates/<slug>.md; gate 2 needs two seats that addressed
each other by `@[[id]]` in text messages, in both directions. Also reports how many text
messages each seat sent (a rough view of whether work was distributed).

This is a preview only. The judged artifact is the console's "Download full session".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from factory.lineup import ROOT, slug  # noqa: E402


def fetch(room: str) -> list[dict]:
    messages, page = [], 1
    while True:
        out = subprocess.run(["band", "room", "messages", room, "--json", "--page", str(page)],
                             capture_output=True, text=True)
        if out.returncode != 0:
            raise SystemExit(out.stderr.strip() or out.stdout.strip())
        batch = json.loads(out.stdout).get("messages", [])
        if not batch:
            return messages
        messages += batch
        page += 1
        if page > 500:
            return messages


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("room")
    ap.add_argument("--mandates", default=str(ROOT / "mandates"))
    args = ap.parse_args()

    msgs = fetch(args.room)
    agents = {m["sender_id"]: m["sender_name"] for m in msgs if str(m.get("sender_type", "")).lower() == "agent"}
    texts = [m for m in msgs if str(m.get("sender_type", "")).lower() == "agent" and m.get("message_type") == "text"]
    edges = {(m["sender_id"], t) for m in texts for t in agents
             if t != m["sender_id"] and f"@[[{t}]]" in str(m.get("content") or "")}
    pairs = sorted({tuple(sorted((agents[a], agents[b]))) for a, b in edges if (b, a) in edges})
    mandates = {slug(p.stem) for p in Path(args.mandates).glob("*.md")}
    missing = sorted(n for n in set(agents.values()) if slug(n) not in mandates)

    print(f"messages: {len(msgs)}   agent seats: {sorted(agents.values())}")
    print("text messages per seat:", dict(Counter(agents[m['sender_id']] for m in texts)))
    print(f"gate 1 seats >= 3: {'ok' if len(agents) >= 3 else 'NO'}")
    print(f"gate 1 mandate per seat: {'ok' if not missing else 'missing ' + ', '.join(missing)}")
    print(f"gate 2 reciprocal @handles: {'ok ' + str(pairs) if pairs else 'NO'}")
    sys.exit(0 if len(agents) >= 3 and not missing and pairs else 1)


if __name__ == "__main__":
    main()
