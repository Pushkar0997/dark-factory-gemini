#!/usr/bin/env bash
# The participant guide's "Before you submit" steps 1–2, against a fresh clone.
#
#   scripts/fresh_clone_check.sh <git url or path> <track> [--no-run]
#
# Clones into a new temp dir (so forgotten files and nested repos show up), runs the official
# `harness check`, then `harness run --all --mode isolated` unless --no-run.
set -euo pipefail

[[ $# -ge 2 ]] || { sed -n 2,7p "$0"; exit 2; }
SRC="$1"; TRACK="$2"; RUN_ALL=1; [[ "${3:-}" == "--no-run" ]] && RUN_ALL=0
BAND_WORK="${BAND_WORK:-$HOME/band-work}"
KICKOFF="${KICKOFF_DIR:-$BAND_WORK/kickoff}"
HPY="${HARNESS_PYTHON:-$BAND_WORK/.venv/bin/python}"
STAMP=$(date +%Y%m%d-%H%M%S)
CLONE="$BAND_WORK/fresh-clone-$STAMP"

git clone -q "$SRC" "$CLONE"
echo "cloned to $CLONE ($(git -C "$CLONE" rev-parse HEAD))"
for d in "$CLONE"/stage-*; do
  [[ -d "$d" ]] || continue
  [[ -n "$(ls -A "$d")" ]] || echo "WARNING: $d is empty in the clone (nested repo or uncommitted files?)"
done
cd "$KICKOFF"
"$HPY" -m harness check "$CLONE" --track "$TRACK"
if [[ $RUN_ALL -eq 1 ]]; then
  "$HPY" -m harness run --track "$TRACK" --repo "$CLONE" --all --mode isolated --out "$BAND_WORK/checks/fresh-$STAMP"
fi
