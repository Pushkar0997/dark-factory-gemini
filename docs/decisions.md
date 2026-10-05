# Decisions

Each entry: the decision, the evidence it rests on, and what it costs. Newest last.

## D1 — Track: `tablekeeper`

**Decision.** Compete in Tablekeeper and stay there.

**Evidence** (from `dark-factory-wearedevs`, read in full 2026-10-05):

| | Tablekeeper | Pocketful |
|---|---|---|
| Spec size, stages 1/2/3/4 (bytes) | 19.4k / 10.5k / 13.1k / 6.3k | 24.5k / 19.7k / 10.1k / 4.4k |
| Shipped share of graded checks, stages 1/2/3/4 | **83 / 41 / 11 / 21 %** | 79 / 35 / 9 / 16 % |
| Shipped test functions, stage 1 / 2 | 91 / 22 | 91 / 31 |
| Stage-2 UI surface | 4 routes: search+grid, signup, login, lookup | 4 routes + authorizations screen, feed, requests, split |
| Hardest stage-1 trap | DST (spring-forward gap, fall-back first occurrence), slot grid | exact split arithmetic, net settlements |
| Hardest late-stage item | stage-4 bounded replanning (≤6 tables, ≤4 pairs, ≤6 bookings: brute force is fine) | stage-3 bitemporal statements with snapshot-stable pagination |

**Why.** With roughly a day left, the realistic scoring range is stages 1–2, maybe 3.
Tablekeeper's stage 1 and 2 are the smaller specs with the larger shipped share, so the
reviewer gets more real feedback per run, and its stage-2 UI (an availability grid) is a
stronger demo with fewer screens. Its traps (DST, idempotency, atomic moves) are precisely
specified, so a reviewer working from a requirements checklist can probe them. Stage 4's
planning problem is explicitly bounded, so exhaustive search is acceptable.

**Cost.** Time-zone handling must be right in every later stage; a DST bug in stage 1 caps
the chain. The reviewer mandate's "probe what the shipped checks do not" step exists for this.

## D2 — Harness: hybrid lineup, Claude Code seats write and verify code

**Evidence.** The Band SDK's `GoogleADKAdapter` bridges only Band platform tools (send
message, participants, memory, …) — checked in `band/adapters/google_adk.py`
(`_build_adk_tools`). The previous Gemini builder/reviewer therefore could not write a file,
commit, or run a check. All six seats configured in Band Desktop run `claude-code-cli`
(`band status`), including the one named `gemini-planner`.

**Decision.** Support three lineups (`factory/lineups.toml`) and recommend **hybrid**:
a Gemini coordinator (Google ADK through `factory-seat`) plus Claude Code implementer and
reviewer. The coordinator's job is reading specs, writing a requirements checklist and
routing — work that fits a messaging-plus-read-only toolset and a cheaper, different model
family. The two seats that must edit, build, commit and run Docker use a full coding harness.
`factory/workspace_tools.py` gives Gemini seats sandboxed files + shell, so an all-Gemini
lineup is possible, but it has not been rehearsed (see FACTORY.md "Known limitations").

**Cost.** Two runtimes to operate, and the Gemini coordinator depends on a Gemini key and its
rate limits. The all-Claude lineup remains a one-command fallback (`prepare_run.sh … claude …`).

## D3 — Mandates are rendered from generic role templates

**Decision.** `factory/mandate_templates/{coordinator,implementer,reviewer}.md` hold the
role text; a lineup fills in seat names, handles, harness and model; `render_mandates.py`
writes `mandates/<seat-slug>.md`; `apply_lineup.py` pins the same model and instructions on
the Band Desktop seats; `factory-seat` refuses to start a Gemini seat whose model differs
from its mandate unless `--allow-fallback` is given.

**Why.** Gate 1 needs one mandate per seat *named after the seat* with the true harness and
model; Gate 4 needs zero track vocabulary. Hand-maintained copies had already drifted (six
files for three roles, all declaring a harness no seat ran). One template per role keeps them
generic, and `run_checks.py` scans them against the organisers' own vocabulary list.

## D4 — The band works in a separate result repo; the submission merges it

**Decision.** Seats commit only into a fresh `~/band-work/<run>/` repository
(`prepare_run.sh`). After the run, `room.json` is committed there and
`assemble_submission.sh` merges that history into this repository with
`--allow-unrelated-histories` — no rebase, squash or amend, so every band commit keeps its
hash, author and message.

**Why.** The guide wants a fresh result repository per judged run, seats that cannot touch
the factory's own files, and a pushed history the seats made. The hand-written
`stage-1..4/` placeholders previously committed here were removed: anything under
`stage-N/` must come from the band.

## D5 — Workspace paths without spaces or `:`

The original checkout lives under `Hackathon - 6:10/`. `uv sync` refuses that path (`path
segment contains separator ':'`) and agent shell commands quote paths inconsistently. All
run state lives under `~/band-work/`; clone the factory to a plain path for real use.
