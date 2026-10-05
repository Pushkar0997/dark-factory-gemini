# Teammate handoff — read this first

Last updated: 2026-10-05 (UTC morning). Deadline: **Mon 2026-10-05 23:59 PDT** (= Tue 06:59 UTC).
Track: **tablekeeper** ([why](decisions.md#d1--track-tablekeeper)). Submitted lineup: **hybrid**.

## 1. Current state (be honest, keep it current)

| Item | State |
|---|---|
| Factory code (`factory/`), lineups, mandate templates, scripts, unit tests | done; `run_checks.py` self-checks pass |
| Claude Code seats `Planner`, `Implementer`, `Reviewer` in Band Desktop | configured: instructions = rendered mandates, model pinned `claude-sonnet-5-5`, cwd `~/band-work` |
| Toy rehearsal 1 (all-Claude, room `add3e832…`, repo `~/band-work/toy-result`) | in progress — see §6 |
| Gemini coordinator (`gemini_planner` via `factory-seat`) | **not runnable yet: `.env` has no `GOOGLE_API_KEY`**; model id `gemini-3.8-flash` unverified |
| Real tablekeeper run | not started |
| `stage-1..4/`, `room.json` in this repo | absent by design until the real run is merged in |

Known problems: see §9.

## 2. Files that matter

`FACTORY.md` (judged) · `mandates/` (judged; generated — never hand-edit) ·
`factory/lineups.toml` (seat ↔ role ↔ harness ↔ model) · `factory/mandate_templates/` (role
text) · `scripts/` (everything you run) · `docs/track-plan.md` (what to verify per stage).

## 3. One-time machine setup

Paths must not contain spaces or `:`. The original checkout under `Hackathon - 6:10/` breaks
`uv sync`; clone to e.g. `~/dark-factory` for real use.

```bash
git clone https://github.com/<org>/dark-factory-gemini ~/dark-factory && cd ~/dark-factory && uv sync
mkdir -p ~/band-work && git clone https://github.com/band-ai/dark-factory-wearedevs ~/band-work/kickoff
uv venv ~/band-work/.venv --python 3.13
uv pip install --python ~/band-work/.venv/bin/python -r ~/band-work/kickoff/harness/requirements.txt
~/band-work/.venv/bin/python -m playwright install chromium
cp .env.example .env                      # fill GOOGLE_API_KEY (Gemini seats only)
cp agent_config.yaml.example agent_config.yaml   # Band agent UUID + band_a_ key per Gemini seat
df -h ~                                   # keep >= 10 GiB free: the first isolated harness run builds a browser image
```

## 4. Commands that are always safe

```bash
uv run python scripts/run_checks.py                         # self-checks, offline
uv run pytest -q                                            # unit tests
uv run python scripts/apply_lineup.py --lineup hybrid --dry-run
band list ; band status --as amaansayydd/implementer        # seat health
band room list ; band room messages <room-id> --type text   # read a room
uv run python scripts/room_precheck.py <room-id>            # gates 1-2 preview on a live room
```

## 5. What only Band Desktop (or a human) can do

- Create seats / Band agents, set a seat's permission mode, sign in.
- Download the room: room ⋮ → Open in Band → ⋮ → Download → **Download full session**
  ([docs/record-room.md](record-room.md)). No CLI does this.
- Record the demo video of the room, a handoff and the result (an eligibility requirement).

## 6. Toy rehearsal

```bash
scripts/prepare_run.sh toy-r2 claude toy           # fresh repo + seat config + dispatch text
cp ~/band-work/kickoff/scaffold/* ~/band-work/toy-r2/stage-1/   # optional, per the guide
```

Create a room with only you and `@planner` (Band Desktop, or
`band chat new --as amaansayydd/planner --with amaansayydd`), then send
`~/band-work/dispatch/toy-r2.md` to the planner (`band room send <room> --mention <planner id> "$(cat …)"`).
Send nothing else. Check: `scripts/run_checks.py --repo ~/band-work/toy-r2 --track toy --stage all`.

**Rehearsal 1 log (all-Claude):** coordinator added both seats itself and sent a verbatim,
self-contained HANDOFF with an R1–R14 checklist; implementer committed `e60f551`
(`toy-stage-1: R1-R14 — …`) and posted a full REVISION. The host disk then filled up (1 GiB
free) and Docker's image store returned I/O errors; the implementer reported a precise
blocker without deleting anything, and the coordinator recorded `STAGE 1 OUTCOME: blocked`
without asking the human — correct dark-factory behaviour. The operator freed ~6 GB of caches,
restarted Docker, and sent one resume message (allowed: rehearsals are not judged). Result of
the resumed loop: _fill in_.

## 7. Real run (judged) — do exactly this

1. Decide the lineup. Hybrid needs a working Gemini key; otherwise use `claude` (one-line
   switch, all mandates re-render). Never change lineup mid-run.
2. `scripts/prepare_run.sh tk-final <lineup> tablekeeper` — prints what it did.
3. If `mandates/` changed: `git add mandates && git commit -m "mandates for <lineup>"`.
4. Hybrid only: in a terminal that stays open,
   `uv run factory-seat --lineup hybrid --role coordinator` and wait for "connected".
   Stop the Band Desktop runtime of `gemini-planner` first (`band stop --as amaansayydd/gemini-planner`)
   so only the Gemini runner answers for that seat.
5. Fresh room with only you + the coordinator. Send `~/band-work/dispatch/tk-final.md`.
   **Then send nothing** — no "continue", no hints, no reruns. The coordinator's per-stage
   `STAGE n OUTCOME` messages are the run's report.
6. While it runs you may *watch* (`band room messages …`) and run checks on committed
   revisions locally. Do not commit into `~/band-work/tk-final`.

## 8. After the run — validate, record, submit

```bash
# per stage, isolated mode (how judging runs)
uv run python scripts/run_checks.py --repo ~/band-work/tk-final --track tablekeeper --stage 1 --isolated --out ~/band-work/checks/tk-final-s1
# then walk docs/track-plan.md's probe list for each claimed stage

# record the room (Band console → Download full session), then:
mv ~/Downloads/<room>.json ~/band-work/tk-final/room.json
grep -nE "band_a_|sk-|AIza|ghp_|Bearer [A-Za-z0-9]{20}" ~/band-work/tk-final/room.json   # rotate + [REDACTED] anything found
git -C ~/band-work/tk-final add room.json && git -C ~/band-work/tk-final commit -m "room.json: full session download"
# delete stage folders that do not claim their stage (only completed stages are submitted)

scripts/assemble_submission.sh ~/band-work/tk-final tablekeeper     # merges band history into this repo
uv run python scripts/run_checks.py --repo . --track tablekeeper --stage all --isolated
git push                                                            # never force-push
scripts/fresh_clone_check.sh https://github.com/<org>/dark-factory-gemini tablekeeper
```

Then: fill FACTORY.md §11 with measured wall time and spend (`band usage`; Gemini usage
from AI Studio), confirm README/FACTORY are not placeholders, re-read every mandate for track
words, submit repo URL + presentation + video on lablab.

## 9. Known problems / risks

- No `GOOGLE_API_KEY` on this machine → hybrid lineup untested; `gemini-3.8-flash` unverified.
- `gemini-planner` agent has both a Band Desktop Claude Code template and SDK credentials;
  running both answers twice. Stop the Desktop worker before starting `factory-seat`.
- `agent_config.yaml` `gemini_builder`/`gemini_reviewer` point at the `claude_builder` /
  `Claude_revierwer` agents (Claude Code seats). The all-Gemini lineup needs new agents.
- Disk: 168 GiB volume, ~14 GiB free after cleanup. Every review builds images; seats are told
  to remove what they build. Check `df -h ~` before the real run.
- Unused seats in Band Desktop (`claude-builder`, `claude-revierwer`, `gemini-planner`) must
  not be added to the judged room: every seat in `room.json` needs a mandate file.
