#!/usr/bin/env bash
# Prepare a fresh, empty result repository and the seats for one factory run, then print
# the dispatch message to paste (or send) to the coordinator.
#
#   scripts/prepare_run.sh <run-name> <lineup> <track>
#   scripts/prepare_run.sh tk-final hybrid tablekeeper
#
# Creates  $BAND_WORK/<run-name>/            (git repo, empty stage-1/, nothing committed by hand)
# Renders  mandates/ for <lineup>: into this repo for a real track (commit it before the run),
#          into the practice repo for the toy
# Applies  owner instructions + pinned models to the lineup's Claude Code seats
# Writes   $BAND_WORK/dispatch/<run-name>.md (the only human input of the run)
#
# Environment: BAND_WORK (default ~/band-work), KICKOFF_DIR (default $BAND_WORK/kickoff).
# Paths must not contain spaces or ':' — agents' shell commands and uv both break on them.
set -euo pipefail

[[ $# -eq 3 ]] || { sed -n 2,14p "$0"; exit 2; }
RUN="$1"; LINEUP="$2"; TRACK="$3"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BAND_WORK="${BAND_WORK:-$HOME/band-work}"
KICKOFF="${KICKOFF_DIR:-$BAND_WORK/kickoff}"
PY="${PYTHON:-$HERE/.venv/bin/python}"
RESULT="$BAND_WORK/$RUN"
HARNESS_PY="${HARNESS_PYTHON:-$BAND_WORK/.venv/bin/python}"

case "$BAND_WORK" in *" "*|*:*) echo "BAND_WORK=$BAND_WORK contains a space or ':'; pick another path" >&2; exit 1;; esac
[[ -d "$KICKOFF/$TRACK/spec" ]] || { echo "no specs at $KICKOFF/$TRACK/spec (set KICKOFF_DIR)" >&2; exit 1; }
[[ -x "$HARNESS_PY" ]] || { echo "harness python $HARNESS_PY missing; see docs/teammate_handoff.md" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon is not reachable; start Docker first" >&2; exit 1; }
FREE_GB=$(df -g "$BAND_WORK" 2>/dev/null | awk 'NR==2{print $4}' || df -BG "$BAND_WORK" | awk 'NR==2{gsub("G","",$4); print $4}')
(( FREE_GB >= 10 )) || { echo "only ${FREE_GB} GiB free under $BAND_WORK; a run needs >= 10 GiB (image builds + browser runner)" >&2; exit 1; }
[[ ! -e "$RESULT" ]] || { echo "$RESULT already exists; a judged run needs a fresh repository" >&2; exit 1; }

mkdir -p "$RESULT/stage-1" "$BAND_WORK/checks" "$BAND_WORK/dispatch"
git -C "$RESULT" init -q -b main
git -C "$RESULT" config user.name "factory-band"
git -C "$RESULT" config user.email "band@factory.local"
echo "created $RESULT"

if [[ "$TRACK" == "toy" ]]; then
  # Practice runs keep their own mandates in the practice repo (as the guide's toy flow
  # does), so rehearsing another lineup never touches this repo's judged mandates/.
  MANDATES="$RESULT/mandates"
  "$PY" "$HERE/scripts/render_mandates.py" --lineup "$LINEUP" --out "$MANDATES"
  git -C "$RESULT" add mandates && git -C "$RESULT" commit -q -m "practice setup: mandates for lineup $LINEUP (human, before dispatch)"
else
  MANDATES="$HERE/mandates"
  "$PY" "$HERE/scripts/render_mandates.py" --lineup "$LINEUP"
  if [[ -n "$(git -C "$HERE" status --porcelain -- mandates)" ]]; then
    echo "NOTE: mandates/ changed for lineup $LINEUP — commit it before dispatching." >&2
  fi
fi
"$PY" "$HERE/scripts/apply_lineup.py" --lineup "$LINEUP" --mandates "$MANDATES"

COORD=$("$PY" -c "import sys; sys.path.insert(0,'$HERE'); from factory.lineup import load_lineup; l=load_lineup('$LINEUP'); print(l.seat('coordinator').handle, l.seat('implementer').handle, l.seat('reviewer').handle)")
read -r C I R <<<"$COORD"

DISPATCH="$BAND_WORK/dispatch/$RUN.md"
cat > "$DISPATCH" <<EOF
You are the coordinator for our factory. Build all four stages of the $TRACK track sequentially, coordinating @$I and @$R, and keeping every stage in its own complete, buildable folder.

Track: $TRACK
Specifications (read each in full; paste the complete text into every handoff):
  $KICKOFF/$TRACK/spec/stage-1.md
  $KICKOFF/$TRACK/spec/stage-2.md
  $KICKOFF/$TRACK/spec/stage-3.md
  $KICKOFF/$TRACK/spec/stage-4.md
Result repository (absolute path; the only place to commit): $RESULT
Stage 1 goes in stage-1/ (empty). When stage N is approved, copy stage-N/ to stage-(N+1)/, delete any nested .git in the copy, and extend the copy to the next specification. Every folder holds its source, a Dockerfile and a RUN.md, and must still satisfy every earlier stage. Never edit an approved folder afterwards.

Checks (the official harness; run from its folder; every --out directory must be new):
  cd $KICKOFF && $HARNESS_PY -m harness run --track $TRACK --repo $RESULT --stage <N> --out $BAND_WORK/checks/$RUN-s<N>-<unique suffix>
Add --mode isolated for the final check of each stage (no network, 2 CPU, 2 GiB — how judging runs). A good stage-N result ends with "claimed stage: N". The next-stage overshoot line is expected to fail. The shipped checks are only part of the graded tests: every requirement in the specification is graded, so build and review against the specification, not the checks.

The reviewer runs the checks independently on the committed revision. After each stage, report the full committed revision and the outcome in the room, then continue with the next stage. This dispatch is the only human input: do not ask me anything; record any blocker and its evidence as the stage outcome.
EOF
echo
echo "dispatch written to $DISPATCH"
echo "next: commit mandates/ if changed, start any Google ADK seat (factory-seat --lineup $LINEUP --role ...),"
echo "      create a fresh room with only you and @$C, and send the dispatch (docs/teammate_handoff.md §Real run)."
