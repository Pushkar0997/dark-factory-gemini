#!/usr/bin/env bash
# Put the Band console's "Download full session" file into a result repository as room.json,
# unchanged, after checking it for credentials. Then commit it there.
#
#   scripts/import_room.sh <downloaded .json> <absolute path of the result repo> [track]
#
# Stops (exit 1) without committing if the official harness credential scan or the stricter
# key scan below finds anything: rotate that credential, replace the value with [REDACTED]
# in room.json by hand, and re-run with that file.
set -euo pipefail

[[ $# -ge 2 ]] || { sed -n 2,10p "$0"; exit 2; }
SRC="$1"; RESULT="$(cd "$2" && pwd)"; TRACK="${3:-tablekeeper}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BAND_WORK="${BAND_WORK:-$HOME/band-work}"
KICKOFF="${KICKOFF_DIR:-$BAND_WORK/kickoff}"
HPY="${HARNESS_PYTHON:-$BAND_WORK/.venv/bin/python}"

python3 - "$SRC" <<'EOF'
import json, sys
room = json.load(open(sys.argv[1]))
msgs = room.get("messages") if isinstance(room, dict) else None
assert isinstance(msgs, list), "not a Band room download: no messages list"
assert room.get("scope", "full") == "full", f"filtered download (scope={room.get('scope')}); use Download full session"
agents = {m.get("senderName") for m in msgs if str(m.get("senderType", "")).lower() == "agent"}
print(f"room download: {len(msgs)} messages, agent seats {sorted(agents)}")
EOF

cp "$SRC" "$RESULT/room.json"

# 1. The organisers' own scan (same code `harness check` runs), on room.json only.
HITS=$(cd "$KICKOFF" && "$HPY" - "$RESULT" <<'EOF'
import pathlib, sys
from harness import check
print("\n".join(p for p in check._credentials(pathlib.Path(sys.argv[1])) if p.startswith("room.json")))
EOF
)
# 2. Stricter: real key shapes the generic scan does not know (Band agent keys, Google,
#    Anthropic, GitHub, OpenAI).
STRICT=$(grep -oE "band_a_[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|sk-ant-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}" "$RESULT/room.json" | sort -u | sed -E 's/^(.{10}).*/\1…/' || true)

if [[ -n "$HITS" || -n "$STRICT" ]]; then
  echo "CREDENTIAL-LIKE CONTENT FOUND — not committing:" >&2
  [[ -n "$HITS" ]] && echo "$HITS" >&2
  [[ -n "$STRICT" ]] && echo "key shapes (truncated): $STRICT" >&2
  exit 1
fi
echo "credential scans: clean"

git -C "$RESULT" add room.json
git -C "$RESULT" commit -q -m "room.json: Band console full-session download, unchanged"
echo "committed room.json in $RESULT ($(git -C "$RESULT" rev-parse --short HEAD))"
"$HERE/.venv/bin/python" "$HERE/scripts/run_checks.py" --repo "$RESULT" --track "$TRACK" | tail -4 || true
