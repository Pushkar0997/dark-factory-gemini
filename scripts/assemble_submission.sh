#!/usr/bin/env bash
# Bring the band's result repository (stage folders + room.json, with the history the seats
# made) into this factory repository, without rewriting either history.
#
#   scripts/assemble_submission.sh <absolute path of the result repo> <track>
#
# Preconditions (checked): this repo has a clean working tree; the result repo has a clean
# tree, room.json committed at its root, no nested .git in stage folders, and touches no
# path this repo already tracks (README.md, FACTORY.md, mandates/ ...).
# The merge is a normal merge commit (--allow-unrelated-histories): every band commit keeps
# its hash, author and message. Nothing is squashed, rebased or amended. Push afterwards.
set -euo pipefail

[[ $# -eq 2 ]] || { sed -n 2,11p "$0"; exit 2; }
RESULT="$(cd "$1" && pwd)"; TRACK="$2"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

fail() { echo "ERROR: $*" >&2; exit 1; }
[[ -z "$(git -C "$HERE" status --porcelain)" ]] || fail "factory repo has uncommitted changes"
[[ -z "$(git -C "$RESULT" status --porcelain)" ]] || fail "result repo has uncommitted changes"
git -C "$RESULT" ls-files --error-unmatch room.json >/dev/null 2>&1 || fail "room.json is not committed in $RESULT (see docs/teammate_handoff.md §Record the room)"
for d in "$RESULT"/stage-*; do [[ ! -e "$d/.git" ]] || fail "$d has its own .git"; done

overlap=$(comm -12 <(git -C "$HERE" ls-files | sort) <(git -C "$RESULT" ls-files | sort) || true)
[[ -z "$overlap" ]] || fail "result repo tracks paths the factory repo also tracks:\n$overlap"

git -C "$HERE" fetch -q "$RESULT" main
git -C "$HERE" merge --allow-unrelated-histories --no-edit -m "Merge the band's $TRACK run (stage folders, room.json) from its result repository" FETCH_HEAD
echo "merged. Now run: python scripts/run_checks.py --repo . --track $TRACK --stage all --isolated"
