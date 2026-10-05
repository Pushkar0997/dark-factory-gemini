# FACTORY.md — a three-seat software factory for Band Desktop

This file is meant to be enough for another team to stand the factory up and point it at a
different problem. The factory knows nothing about any particular problem: the problem
arrives as one dispatched task containing its specification.

## 1. Architecture

```
 human ── one dispatch per run (task + spec paths + repo path + check command) ──┐
                                                                                 ▼
                                                        ┌──────────────────────────────┐
                                                        │ coordinator                  │
                                                        │ requirements checklist R1..Rn│
                                                        │ handoffs · loop · final report│
                                                        └───────┬──────────────▲───────┘
                              HANDOFF (spec verbatim + R-list)  │              │ VERDICT
                                                                ▼              │
 ┌──────────────────────────────┐   REVISION <full sha> + evidence   ┌─────────┴────────────┐
 │ implementer                  │ ─────────────────────────────────► │ reviewer             │
 │ code · own tests · Dockerfile│ ◄───────────────────────────────── │ clean worktree @ sha │
 │ RUN.md · commits             │   VERDICT CHANGES REQUIRED D1..Dn  │ build · harness ·    │
 └──────────────┬───────────────┘                                    │ probe unchecked R's  │
                │ commits                                            └──────────────────────┘
                ▼
     result repository (one folder per stage; stage-N+1 = approved stage-N copied, extended)
```

Three roles, each owned by exactly one seat:

| Role | Owns | Never does |
|---|---|---|
| coordinator | requirements digest (numbered checklist), self-contained handoffs, the review loop, stage order, the final report | writes or commits product code; runs the reviewer's checks for it |
| implementer | source, its own tests per checklist item, Dockerfile, RUN.md, commits | approves its own work; edits an approved folder |
| reviewer | the accept/reject verdict, from evidence it gathered itself on a clean checkout of the reported hash | fixes code; approves on the implementer's word |

Role texts: `factory/mandate_templates/`. The rendered, seat-named copies the judges read:
`mandates/`.

## 2. Seats, harnesses and models (lineups)

A **lineup** (`factory/lineups.toml`) maps the three roles onto real Band seats:

| Lineup | coordinator | implementer | reviewer | Status |
|---|---|---|---|---|
| `hybrid` (recommended) | `gemini_planner` — Google ADK via `factory-seat`, `gemini-3.8-flash` | `Implementer` — Claude Code, `claude-sonnet-5-5` | `Reviewer` — Claude Code, `claude-sonnet-5-5` | coordinator path not yet rehearsed live (needs a Gemini key) |
| `claude` (**judged run**) | `Planner` — Claude Code, `claude-sonnet-5-5` | `Implementer` — Claude Code, `claude-opus-5-5` | `Reviewer` — Claude Code, `claude-opus-5-5` | toy rehearsed (on sonnet); used for the judged tablekeeper run |
| `gemini` | Google ADK | Google ADK + workspace tools | Google ADK + workspace tools | experimental, not rehearsed |

Why hybrid: the coordinator reads, plans and routes — a messaging-plus-read-only toolset on a
cheaper model from a different vendor is enough, and a second model family reviewing the plan
reduces correlated blind spots. The implementer and reviewer must edit files, run Docker and
Git and drive a browser test runner; they run in a full coding harness. Every lineup uses the
same three role mandates, so switching lineups changes no protocol.

**Model truthfulness.** `mandates/<seat>.md` starts with `Harness:` and `Model:`. The same
values drive execution: `apply_lineup.py` pins the model on each Claude Code seat's Band
runtime template and installs the mandate as its owner instructions; `factory-seat` reads the
Gemini seat's model from its mandate, verifies it against the Gemini API before connecting,
and refuses a different model unless `--allow-fallback` is passed (then it logs `MODEL
MISMATCH` — a run made that way must not be submitted without re-rendering the mandates).
After a run, the model actually used is checked, not assumed: Claude Code records it on every
response (`grep -o '"model":"[^"]*"' ~/.claude/projects/-Users-<you>-band-work/*.jsonl | sort | uniq -c`;
toy rehearsal 1: only `claude-sonnet-5-5`), and `factory-seat` logs the Gemini model at start.

## 3. Setup (≈20 minutes)

Prerequisites: Python 3.12+, Git, Docker (daemon running), [uv](https://docs.astral.sh/uv/),
Band Desktop ≥ 0.4.10 with the `band` CLI, and the event kickoff repository. Use paths with
no spaces or `:` (uv and agent shell commands break on them).

```bash
git clone <this repo> ~/dark-factory && cd ~/dark-factory && uv sync    # factory runtime + tests
mkdir -p ~/band-work && cp -R <kickoff checkout> ~/band-work/kickoff     # specs + harness
uv venv ~/band-work/.venv --python 3.13
uv pip install --python ~/band-work/.venv/bin/python -r ~/band-work/kickoff/harness/requirements.txt
~/band-work/.venv/bin/python -m playwright install chromium
```

Band Desktop seats:

1. Create the Claude Code seats your lineup names (Band Desktop → New local agent → Claude
   Code). Name them exactly as in `lineups.toml` (`name`), or edit the lineup to match yours —
   the mandate file name is derived from the display name.
2. Set each Claude Code seat's working directory to `~/band-work` and permission mode to
   auto (unattended runs stall on permission prompts otherwise).
3. For a Google ADK seat: create the agent in the Band console, put its UUID and API key in
   `agent_config.yaml` (copy `agent_config.yaml.example`), and your Gemini key in `.env`
   (copy `.env.example`). If the agent also has a Band Desktop runtime template, stop that
   worker (`band stop --as <owner>/<handle>`) so only one runtime answers for the seat.

Then, per run:

```bash
scripts/prepare_run.sh <run-name> <lineup> <track>     # fresh result repo, mandates, seat config, dispatch text
git commit -am "mandates for <lineup>"                   # if prepare_run re-rendered them
uv run factory-seat --lineup hybrid --role coordinator   # only for Google ADK seats; keep it running
```

Create a fresh room containing only you and the coordinator, and send the dispatch text
(`~/band-work/dispatch/<run-name>.md`) to the coordinator. Do nothing else until its final
report. The coordinator adds the other seats.

## 4. Handoff protocol

Seats see only messages addressed to them, so every handoff is self-contained:

- **HANDOFF** (coordinator → implementer): repository path, target folder, base folder, the
  complete specification pasted verbatim (split into numbered parts, last part marked
  `END OF HANDOFF`), the numbered requirements checklist, decisions taken on ambiguous points,
  the exact check commands, and the definition of done.
- **REVISION** (implementer → reviewer + coordinator): full 40-character commit hash, folder,
  the requirements as received, which checklist items are covered and by which test, known
  gaps, commands run with results, the run command.
- **VERDICT** (reviewer → implementer + coordinator): hash, commands run with results,
  checklist status per item, numbered defects `D1..Dn` each with requirement id, expected,
  observed and a reproduce command; `APPROVED` or `CHANGES REQUIRED`.

All three use literal `@handles`. Before the first handoff the coordinator confirms the other
two seats are in the room and adds any that are missing; if a mention is rejected because a
seat is absent it adds the seat and resends once, then records the error as an outcome.

## 5. Review protocol — how bad work is caught

The reviewer's verdict rests only on what it did itself:

1. `git worktree add` of the exact reported hash into a scratch directory (nothing
   uncommitted can influence it); check for nested `.git` in the folder.
2. Build the container from scratch per RUN.md; confirm it becomes healthy.
3. Run the official harness for this stage and all earlier ones against that worktree (so
   the result belongs to the exact hash); the stage's final verdict uses `--mode isolated`
   (no network, 2 CPU, 2 GiB — the judging environment).
4. Walk the checklist; for every item the shipped checks do not exercise, probe the running
   service directly (crafted, malformed and concurrent requests; reset; upgrade from an
   earlier stage's export) and record what it observed.
5. Read the diff since the last approved revision for special-casing of known inputs,
   swallowed errors, races and regressions.

Approval requires a clean build and start, all shipped checks for this and earlier stages
passing in the reviewer's own run, and no checklist item known to fail. What could not be run
is reported as not run, never as a pass.

The requirements checklist is the factory's main defence against the hidden part of the
grading: the guide states every graded test is written in the specification, and the
shipped checks cover as little as 11% of a stage. Each `R` item is an obligation the
implementer must test and the reviewer must probe, whether or not a shipped check touches it.

## 6. Failure handling, retries and autonomy

| Failure | What happens |
|---|---|
| Reviewer rejects | Coordinator pastes the full defect list back to the implementer; fix → new commit → new REVISION listing each defect id; reviewer re-verifies. Max **4** cycles per stage, then the coordinator records the best evidenced revision and the open defects as the outcome and moves on |
| Incomplete handoff | Receiver asks the coordinator for exactly the missing content; the coordinator resends marked `RESEND`, never a second work item |
| Seat absent from room | Coordinator adds it and retries once; then records the error |
| Model 429 / 5xx / timeout (Gemini seats) | Bounded retry with jittered exponential backoff, honouring the server's retry delay; see §7 |
| Blocker nobody can clear | Coordinator records blocker + evidence as `STAGE n OUTCOME: blocked` and continues where possible |

No seat may ask the human anything or wait for a human reply between dispatch and the final
report; every mandate says so. Commits are never amended, rebased or squashed.

## 7. Rate limiting (Google ADK seats)

`factory/adapter.py` (`ResilientGoogleADKAdapter`), tuned through environment variables
(`.env.example`):

| Variable | Default | Effect |
|---|---|---|
| `FACTORY_MAX_RETRIES` | 6 | total attempts per turn |
| `FACTORY_INITIAL_BACKOFF` | 5 s | wait before the 2nd attempt |
| `FACTORY_BACKOFF_FACTOR` | 2 | 5, 10, 20, 40, 80 s … |
| `FACTORY_MAX_BACKOFF` | 90 s | cap for one wait |
| `FACTORY_JITTER` | 0.25 | each wait randomised ±25% so seats do not retry in lockstep |
| `FACTORY_TURN_DELAY` | 2 s | minimum gap between two turns of one seat (burst smoothing) |

- Retried: HTTP 408/429/5xx and errors naming resource exhaustion, quota, overload,
  unavailability or timeouts. Not retried: 400/401/403/404 and anything else (bugs surface).
- A `retryDelay`/`retry in Ns` hint from the API raises the wait to that value (capped).
- **No duplicate work:** if a turn already sent a message or wrote a file before failing,
  the retry is told exactly which tool calls completed and to continue from there, instead of
  replaying the turn.
- **Same model on every attempt.** Exhausted retries post a failure to the room and log room,
  seat and model; nothing is swallowed.
- Tuning: on a free-tier key with one Gemini seat the defaults keep a worst case under ~4
  minutes per turn. If 429s persist, raise `FACTORY_TURN_DELAY` first (it reduces the rate
  rather than reacting to it), then `FACTORY_INITIAL_BACKOFF`.

Claude Code seats' rate limiting is handled by Claude Code itself.

## 8. Workspace tools for Gemini seats

The Band SDK's ADK adapter only exposes Band platform tools. `factory/workspace_tools.py`
adds `readfile`, `listdir` (coordinator and up), `writefile` and `runcommand` (implementer and
reviewer), confined to `FACTORY_WORKSPACE`: paths are resolved (symlinks included) and
refused outside the root; commands get a timeout (≤ 30 min), truncated output and an
environment with every `*KEY*/*TOKEN*/*SECRET*/*PASSWORD*` variable removed, so a command
cannot print a credential into the room. These are guard rails, not a security boundary —
run such seats on a machine or Docker Sandbox you accept them changing.

## 9. Evidence, commits and stage progression

- The implementer commits in meaningful steps, authored as its seat, with messages naming
  the work item and the checklist items covered (`stage-2: R4 R9 — …`). The first commit of a
  new stage is the unchanged copy of the approved previous folder, so the diff of the
  extension is reviewable on its own.
- REVISION and VERDICT messages carry full hashes, which ties every commit to the room.
- Stage N+1 starts only after the reviewer approved stage N by hash; the approved folder is
  never edited again. Each folder must still pass every earlier stage's checks.
- The coordinator posts one `STAGE n OUTCOME` per stage, including the review cycle count.

## 10. Operating the factory (validation)

```bash
uv run python scripts/run_checks.py                                   # self-checks: unit tests, lineups, mandates vs organiser vocabulary, hygiene
uv run python scripts/run_checks.py --repo ~/band-work/<run> --track <track> --stage 1 --isolated
scripts/assemble_submission.sh ~/band-work/<run> <track>              # merge the band's history in, after room.json is committed there
scripts/fresh_clone_check.sh <github url> <track>                     # guide's "before you submit" 1–2 on a fresh clone
```

## 11. Measurements

Only measured numbers are recorded here.

| Run | Lineup | Result | Wall time | Spend (Band `usage rooms`, list-price estimate, not a bill) |
|---|---|---|---|---|
| **judged tablekeeper run**, room `7c5f1e66…`, 2026-10-05 | claude: coordinator `claude-sonnet-5-5`, implementer + reviewer `claude-opus-5-5` (confirmed from the seats' transcripts) | stage 1 approved at `d67a068` after one rejection (below); stage 2 in progress at time of writing | stage 1: **14 min 22 s** dispatch (06:42:35 UTC) → `STAGE 1 OUTCOME: approved` (06:56:57), no human input. Then idle 3 h 49 min on a provider usage limit (§12) | snapshot 13:07 UTC: 13.0 M tokens, **$9.74**: implementer $5.38 · reviewer $3.39 · coordinator $0.98 |
| toy rehearsal 1, 2026-10-05 | claude, all `claude-sonnet-5-5` | 4/4 stages approved by the reviewer; operator re-check `harness run --all --mode isolated`: every folder claims its stage | 23 min 40 s dispatch → final report, of which ~7.6 min stalled on a full host disk (see §12) | 7.73 M tokens, **$2.92**: implementer $1.12 · reviewer $1.06 · coordinator $0.74 |

Toy rehearsal 1 exercised: seat self-recruitment by the coordinator, verbatim self-contained
handoffs with numbered checklists (R1–R39 over four stages), one commit per stage copy plus
one per extension, reviewer verification on a clean worktree in host and isolated mode
(including the stage-2 browser suite), machine-failure escalation as a recorded blocker.
It did **not** exercise a rejection: every revision passed review first time on this small
problem. The real track is where the reject → fix loop is expected to matter.

**A bad result the factory caught (judged run, stage 1).** The implementer reported
`cdfdb64` (full API, its own tests passing, shipped harness green). The reviewer rebuilt it
from a clean worktree, probed beyond the shipped checks, and answered
`VERDICT tablekeeper-stage-1 cdfdb647…: CHANGES REQUIRED` with three defects, each with a
reproduce command: **D1** 500 responses at calendar edges, **D2** HEAD/OPTIONS returning
non-JSON errors, **D3** a non-integer `party_size` accepted on PATCH and moves. The
coordinator sent `FIX REQUEST tablekeeper-stage-1 (cycle 1 of max 4)` with the full defect
list; the implementer fixed all three with regression tests in `d67a068`
(`fix D1 calendar-edge 500s, D2 HEAD/OPTIONS JSON errors, D3 non-integer party_size on
PATCH/moves`); the coordinator sent a `RE-REVIEW HANDOFF`; the reviewer re-verified and
approved. Elapsed from verdict to approval: about 4 minutes. None of the three defects was
caught by the shipped checks.

## 12. Design trade-offs and what did not work

- **Gemini seats as code writers (tried, replaced as default).** The first version ran all
  three seats on Google ADK with only Band messaging tools; the builder could not write a
  file or run a check, so it could only *describe* code. Workspace tools fix the capability,
  but a home-grown tool loop is less proven than a coding harness, so the default keeps
  Gemini on coordination.
- **Hand-maintained mandates (replaced).** Six mandate files for three roles drifted from the
  seats actually configured. Rendering from templates removed the drift.
- **One seat per role, three seats total.** More seats add handoff cost without adding
  independent judgment; the rubric scores distribution of real work, not seat count.
- **Review cost.** Building the container and running the isolated harness on every
  revision is slow (the first isolated run builds a browser-runner image), but it is the
  only verdict that matches how judging runs.
- **Requirements checklist instead of test-driven review.** Costs coordinator tokens per
  stage; buys coverage of what the shipped checks never ask.
- **Machine failures are outcomes, not questions (learned).** In toy rehearsal 1 the host
  disk filled and Docker's image store failed. The implementer reported the exact error and
  refused to prune data it did not own; the coordinator recorded `STAGE 1 OUTCOME: blocked`
  without asking the human. Mandates now also require seats to remove only the containers
  and images they created, and `prepare_run.sh` refuses to start with < 10 GiB free.
- **A provider usage limit stalled the run, and a human restarted it (judged run).** At
  07:03 UTC the implementer's Claude Code turn failed with `You've hit your session limit ·
  resets 4:20pm`. Band recorded the failed turn, but nothing in the factory re-wakes a seat
  when the limit resets, and the coordinator only acts on incoming messages, so all three
  seats sat idle for 3 h 49 min. At 10:52 UTC the operator posted `continue your work` to the
  three seats. **That message is human input after dispatch: stage 1 is a clean dark-factory
  run; stage 2 onward in this room is not, and we do not claim it is.** Fixes we would make:
  a watchdog that re-posts the last handoff to a seat whose turn failed with a rate or usage
  limit once the limit resets (the same duplicate-safe resume `factory-seat` already does for
  Gemini 429s), and a cheaper model on the implementer for long runs.
- **Reviewer runs the harness on its own worktree (learned).** In the rehearsal the reviewer
  built from a clean worktree but pointed the harness at the shared repository; the mandate
  now requires the worktree so the result belongs to the exact hash.

## 13. Known limitations

- The hybrid coordinator (Gemini) has not completed a live run yet; the toy was rehearsed on
  the all-Claude lineup. Its Band connection is verified (`factory-seat` connects as
  `gemini_planner` and loads its mandate); the Gemini model call is not. `gemini-3.8-flash` is the configured id, not yet verified against
  the API from this machine (no key present at the time of writing); `factory-seat` verifies
  it at startup.
- The all-Gemini lineup is untested end to end.
- No automatic resume after a Claude Code usage limit (see §12): a long unattended run on a
  subscription can stop until a human nudges it, which breaks autonomy.
- `agent_config.yaml` entries `gemini_builder`/`gemini_reviewer` currently point at agents
  whose Band Desktop seats are Claude Code; dedicated agents are needed for the gemini lineup.
- Long specifications are pasted into handoffs in parts; a coordinator model with a small
  output budget may need several turns per handoff.
