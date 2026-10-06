# Final Submission Compliance Audit: Dark Factory (`tablekeeper`)

**Repository**: `Pushkar0997/dark-factory-gemini`  
**Audit Date**: 2026-10-06  
**Auditor**: Antigravity Compliance Auditor  
**Overall Status**: **PASS** (Zero Disqualifying Flaws; Complete Audit Trail)

---

## 1. Repository State

- **Current Branch**: `main`
- **Remote Tracking**: `origin/main` (`https://github.com/Pushkar0997/dark-factory-gemini.git`)
- **Pre-Audit HEAD Commit**: `b78333dab35af634abe43492affa78ef33b0a214` (`feat(deploy): configure Replit deployment for Stage 4 Tablekeeper demo`)
- **Working Tree State**: Clean; all sensitive credentials (`.env`, `agent_config.yaml`) are untracked and verified git-ignored.
- **Result Repository Structure**:
  - `factory/`: Core factory runtime, mandate templates, and lineup definitions.
  - `mandates/`: Rendered seat mandates matching the judged run.
  - `scripts/`: Self-check, room import, and validation tooling.
  - `docs/`: Decisions, handoff logs, deployment guides, and compliance audits.
  - `stage-1/`, `stage-2/`, `stage-3/`, `stage-4/`: Complete, autonomous Band-generated applications.
  - `room.json`: Raw cryptographic full-session log exported directly from Band Desktop.
  - `.replit`, `replit.nix`, `requirements.txt`: Lightweight, read-only demo deployment layer.

---

## 2. Judged Room Identity

- **Band Room UUID**: `7c5f1e66-ce31-4567-a0d5-3048c5ccef3a`
- **Room Title**: `Oct 5, 2026 at 12:12:33 PM`
- **Export Timestamp**: `2026-10-05T16:47:33.442Z` (`scope: full`, unpruned download)
- **Result Repository Path During Run**: `/Users/amaansayydd/band-work/tk-final`
- **Run Timing**:
  - Dispatched: `2026-10-05T06:42:35.494Z`
  - Stage 1 Approved: `2026-10-05T06:56:26.146Z`
  - Stage 2 Approved: `2026-10-05T13:30:40.529Z`
  - Stage 3 Approved: `2026-10-05T16:07:25.818Z`
  - Stage 4 Approved: `2026-10-05T16:17:42.431Z`
  - Active Compute Time: **55.7 minutes**
  - Total Wall Time: **9 hours 35 minutes** (due to two Claude subscription usage limit stalls and one network disconnect)

---

## 3. Actual Agent Lineup

The repository defines three lineups in [`factory/lineups.toml`](../factory/lineups.toml). The **canonical lineup that executed the judged run** is the **`claude`** lineup:

| Seat Name | Handle | Role | Harness | Pinned Model | Band Seat ID |
|---|---|---|---|---|---|
| **Planner** | `@planner` | Coordinator | Claude Code | `claude-sonnet-5-5` | `d7182d3f-e89b-43fc-bf37-c1d23b630dd2` |
| **Implementer** | `@implementer` | Implementer | Claude Code | `claude-opus-5-5` | `de4a13b3-14b3-415a-8d86-6c53c523936f` |
| **Reviewer** | `@reviewer` | Reviewer | Claude Code | `claude-opus-5-5` | `d82db090-80a6-41b6-868a-e975223f6563` |

### Truthfulness & Alignment:
- Rendered files in [`mandates/`](../mandates/) (`planner.md`, `implementer.md`, `reviewer.md`) match the `claude` lineup **100% byte-for-byte** (confirmed by `scripts/run_checks.py`).
- Models were verified from the Claude Code session transcripts (`grep -ho '"model":"[^"]*"' ~/.claude/projects/-Users-*-band-work/*.jsonl`).
- **Hybrid / Gemini Note**: The repository includes infrastructure for a Gemini coordinator (`gemini-3.8-flash`) via Google ADK (`factory-seat`). However, because no Gemini API key was present at dispatch time, the factory operated on the verified `claude` lineup. This is openly disclosed in [`README.md`](../README.md) and [`FACTORY.md`](../FACTORY.md).

---

## 4. Stage Authorship & Git History Audit

### Rule Compliance:
All code and test assets inside `stage-1/`, `stage-2/`, `stage-3/`, and `stage-4/` were produced exclusively by the autonomous Band **Implementer** seat.

### Complete Commit Ledger Touching Stage Directories:

| Commit | Author | Timestamp | Commit Message / Stage Work |
|---|---|---|---|
| `c22ddf2` | `Implementer <implementer@factory.local>` | 2026-10-05 12:13:42 +0530 | `tablekeeper-stage-1: R1 R2 R3(partial) — minimal service with health and reset` |
| `cdfdb64` | `Implementer <implementer@factory.local>` | 2026-10-05 12:19:03 +0530 | `tablekeeper-stage-1: R3-R16 — full reservations API, idempotency, DST, moves, export/import, tests` |
| `d67a068` | `Implementer <implementer@factory.local>` | 2026-10-05 12:24:44 +0530 | `tablekeeper-stage-1: R4 R8 R10 R13 R16 — fix D1 calendar-edge 500s, D2 HEAD/OPTIONS JSON errors, D3 non-integer party_size on PATCH/moves` |
| `b6bcbb7` | `Implementer <implementer@factory.local>` | 2026-10-05 12:26:57 +0530 | `tablekeeper-stage-2: copy stage-1 to stage-2` |
| `bf61c22` | `Implementer <implementer@factory.local>` | 2026-10-05 16:22:58 +0530 | `tablekeeper-stage-2: R26 R27 R28 R29 R30 R31 R32 — combined tables API, table_ids, stage-1 import compatibility` |
| `5e829fc` | `Implementer <implementer@factory.local>` | 2026-10-05 16:26:56 +0530 | `tablekeeper-stage-2: R17-R25 — browser UI (search grid, combos, booking with idempotent retry, lookup)` |
| `de1731b` | `Implementer <implementer@factory.local>` | 2026-10-05 16:27:57 +0530 | `tablekeeper-stage-2: R20 R21 R22 R24 R25 — browser tests for out-of-order search, lost response retry, upgrade, combos, 375px` |
| `5f617a7` | `Implementer <implementer@factory.local>` | 2026-10-05 19:01:23 +0530 | `tablekeeper-stage-3: copy stage-2 to stage-3` |
| `3c86ab1` | `Implementer <implementer@factory.local>` | 2026-10-05 19:06:13 +0530 | `tablekeeper-stage-3: R33-R46 — policies, accepted terms/revision, explain, history/decision, series, moves under policies` |
| `101956e` | `Implementer <implementer@factory.local>` | 2026-10-05 19:09:00 +0530 | `tablekeeper-stage-3: R33-R47 — stage-3 tests, policy-aware grid labels, selected-cell contrast` |
| `0fff21e` | `Implementer <implementer@factory.local>` | 2026-10-05 21:38:19 +0530 | `tablekeeper-stage-4: copy stage-3 to stage-4` |
| `a0ebb6d` | `Implementer <implementer@factory.local>` | 2026-10-05 21:41:34 +0530 | `tablekeeper-stage-4: R48-R57 — restaurant revision, closures, replans preview/apply, series amend, upgrade defaults` |
| `b6ae92f` | `Implementer <implementer@factory.local>` | 2026-10-05 21:44:14 +0530 | `tablekeeper-stage-4: R48-R58 — stage-4 tests, policy-aware seat labels in the grid` |

### Stage Integrity Verification:
- **`git diff b6ae92f..HEAD -- stage-1 stage-2 stage-3 stage-4`**: **EMPTY (0 lines changed)**.
- **Git History Rewrite Check**: **CLEAN**. No rebasing, squashing, or amending occurred. The Band's history was merged into the factory repository via `git merge --allow-unrelated-histories` at commit `97c4653`.

---

## 5. Human Commits Audit

Every human commit in the repository history has been verified and classified:

| Commit | Author | Category | Verification & Legitimacy |
|---|---|---|---|
| `5d25823` | Pushkar Kumar | B | Factory scaffolding and fallback adapter. |
| `6b89e70` | Pushkar Kumar | B | Expansion into multi-agent factory trio. |
| `a6f38a8` | Pushkar Kumar | B | Repository reorganization for competition compliance. |
| `ce04bac` | Pushkar Kumar | B | Rate-limit adapter resiliency and entrypoint consistency. |
| `0eecc64` | Amaan Sayyed | B | Sandboxed workspace tools and duplicate-safe retries. |
| `0f699eb` | Amaan Sayyed | B | Generic role templates, lineups, and mandate rendering. |
| `f0a7ff3` | Amaan Sayyed | C | Documentation: run book, FACTORY.md. |
| `bb04831` | Amaan Sayyed | B | Mandate requirement: reviewer uses isolated clean worktrees. |
| `a007de5` | Amaan Sayyed | B | Added official credential scan to `run_checks.py`. |
| `ab2f706` | Amaan Sayyed | B | `room_precheck.py` preview tooling. |
| `67cd246` | Amaan Sayyed | C | Documentation: toy rehearsal 1 results and metrics. |
| `8467f13` | Amaan Sayyed | C | Documentation: verified models from transcripts. |
| `9e22823` | Amaan Sayyed | B | Rendered mandates for judged `claude` lineup. |
| `42d547b` | Amaan Sayyed | C | FACTORY.md disclosure of stage-1 rejection and stalls. |
| `45d8be3` | Amaan Sayyed | C | FACTORY.md §11 full measurements and human input disclosure. |
| `e8d82fd` | Amaan Sayyed | B | `scripts/import_room.sh` credential guard tool. |
| `85d5312` | factory-band | A/B | Committed unpruned `room.json` download. |
| `97c4653` | Amaan Sayyed | B | Clean merge of Band result repository into factory repository. |
| `044e87b` | Amaan Sayyed | B | Added author hygiene check to `run_checks.py`. |
| `b207c62` | Amaan Sayyed | C | Updated handoff notes after fresh-clone verification. |
| `b78333d` | Pushkar Kumar | C | Replit deployment configuration and live demo docs. |

**Classification Summary**:
- **A (Band-generated stage code)**: Commits `c22ddf2` through `b6ae92f` (all by Implementer).
- **B (Human-required submission artifact)**: Tooling, mandates, run scripts, and merge.
- **C (Documentation / configuration only)**: README, FACTORY.md, handoffs, Replit configs.
- **D (Potentially problematic modifications to judged code)**: **NONE**. Exactly 0 commits.

---

## 6. Potentially Problematic Commits Audit

Special audit of commit **`b78333d`** (`feat(deploy): configure Replit deployment for Stage 4 Tablekeeper demo`):
- **Files Modified**:
  - `.replit`: Configures runtime entrypoint (`python stage-4/app.py`) and port mapping.
  - `replit.nix`: Declares Nix dependencies (`python312Full`, `tzdata`).
  - `requirements.txt`: Declares `tzdata>=2024.1` for pip.
  - `pyproject.toml` / `uv.lock`: Synchronized `tzdata` dependency.
  - `README.md` / `docs/replit_deployment.md`: Added public deployment instructions.
- **Stage Code Impact**: **ZERO**. Files inside `stage-1/` through `stage-4/` were never modified or staged.
- **Verdict**: Completely safe, decoupled, and compliant.

---

## 7. `room.json` Audit

The exported `room.json` (978 KB, 767 events) contains the complete, unpruned message stream:

### Participant Roster & Event Counts:
- **Total Events**: 767
  - `tool_call`: 244
  - `tool_result`: 243
  - `task`: 143
  - `thought`: 82
  - `text`: 47
  - `participant`: 4
  - `error`: 4
- **Text Messages Sent by Agents**:
  - `Planner`: 22
  - `Implementer`: 13
  - `Reviewer`: 9

### Complete Log of Human Participant Activity:
There are exactly 5 events involving human users across the entire session:
1. **Event #0** (`2026-10-05T06:42:34.057Z`): `Amaan Sayyed joined the conversation`.
2. **Event #1** (`2026-10-05T06:42:35.494Z`): Initial Dispatch text from Amaan Sayyed to `@planner`. Verbatim task assignment specifying track (`tablekeeper`), specs paths, and isolation requirements.
3. **Event #270** (`2026-10-05T10:51:01.684Z`): `Pushkar Kumar joined the conversation` (0 messages sent).
4. **Event #271** (`2026-10-05T10:52:48.023Z`): Administrative resume message from Amaan Sayyed:
   > `@implementer @reviewer @planner continue your work`  
   *(Context: Following a 3h 49m idle stall caused by Claude subscription rate limits resetting at 10:50 UTC).*
5. **Event #392** (`2026-10-05T13:29:05.712Z`): Network disconnect recovery message from Amaan Sayyed:
   > `@reviewer your verification of de1731b134084539c569e81a67d84546b0ae6a36 was interrupted by a network error (ENOTFOUND) at 11:03 UTC; please resume it and send your verdict.`  
   *(Context: Following a 2h 25m idle pause when Reviewer's API call dropped on socket ENOTFOUND).*

### Collaboration & Defect Catch Evidence:
- **Planner Requirements Digest**: Planner broke specifications into explicit numbered obligations (`R1`–`R58`) passed via self-contained handoffs.
- **Genuine Rejection and Fix (Stage 1)**:
  - Implementer reported revision `cdfdb64` claiming full Stage 1 passing.
  - Reviewer independently tested on a clean worktree and rejected the revision with:
    `VERDICT tablekeeper-stage-1 cdfdb647...: CHANGES REQUIRED` (citing **D1**: calendar-edge 500s, **D2**: HEAD/OPTIONS non-JSON responses, and **D3**: non-integer party sizes on moves).
  - Planner issued `FIX REQUEST tablekeeper-stage-1 (cycle 1 of max 4)` with the full defect report.
  - Implementer fixed all three defects in `d67a068` with regression tests.
  - Reviewer re-tested in a clean worktree and issued `VERDICT: APPROVED` in ~4 minutes.
  - *Crucial note*: The shipped test suite never caught D1, D2, or D3; the Reviewer caught them independently.
- **Stage Progression Across Stages 2, 3, 4**:
  - Reviewer notes on selected-cell contrast in Stage 2 were proactively fixed by Implementer in Stage 3.
  - Reviewer note on availability grid seat labels was turned into requirement `R58` by Planner and implemented in Stage 4.

---

## 8. Stage 1–4 Validation Evidence

Operator re-validation using the official competition harness in isolated mode (`--mode isolated`, 2 CPU, 2 GiB, no network) on a clean clone:

| Stage | Shipped Check Suite | Pass Rate | Result Status |
|---|---|---|---|
| **Stage 1** | Suite 1 | **120 / 120** | Claims Stage 1 |
| **Stage 2** | Suite 1 + Suite 2 | **145 / 145** (120/120, 25/25) | Claims Stage 2 |
| **Stage 3** | Suite 1 + 2 + 3 | **152 / 152** (120/120, 25/25, 7/7) | Claims Stage 3 |
| **Stage 4** | Suite 1 + 2 + 3 + 4 | **158 / 158** (120/120, 25/25, 7/7, 6/6) | Claims Stage 4 |

---

## 9. Factory Compliance (Official Gates)

- **Gate 1: Agent Seats >= 3 with Matching Mandates**:
  - `room.json` contains exactly 3 agent seats: `Planner`, `Implementer`, `Reviewer`.
  - Matching mandates exist in `mandates/`: `planner.md`, `implementer.md`, `reviewer.md`.
  - **Verdict**: **PASS**.
- **Gate 2: Reciprocal `@handle` Communication**:
  - Verified edges in `room.json`:
    - `Planner` <--> `Implementer` (bidirectional)
    - `Implementer` <--> `Reviewer` (bidirectional)
    - `Planner` <--> `Reviewer` (bidirectional)
  - All 3 pairs exchanged reciprocal messages with explicit mentions.
  - **Verdict**: **PASS**.
- **Gate 4: Generic / Spec-Driven Mandates (Zero Track Vocabulary)**:
  - Scanned `mandates/*.md` for track-specific keywords (`tablekeeper`, `pocketful`, `restaurant`, `reservation`, `dining`, etc.).
  - Total hits: **0**. Mandates are strictly generic role definitions.
  - **Verdict**: **PASS**.

---

## 10. Teamwork Evidence

| Teammate | Primary Responsibilities & Evidence |
|---|---|
| **Pushkar Kumar** | Factory initialization (`5d25823`, `6b89e70`), repository compliance structure (`a6f38a8`), rate-limit adapter (`ce04bac`), and public Replit live demo deployment layer (`b78333d`). |
| **Amaan Sayyed** | Sandboxed workspace tools (`0eecc64`), generic mandate templates and lineups (`0f699eb`, `9e22823`), live Band Desktop operation, session download verification, and submission assembly (`97c4653`). |

---

## 11. Application & Demo Status

- **Local Container Execution**: Each stage contains a self-contained `Dockerfile` and `RUN.md`. Verified that containers bind to `0.0.0.0:$PORT` and require no external services or DB setup.
- **Replit Live Demo Layer**:
  - Configured via `.replit`, `replit.nix`, and `requirements.txt`.
  - Entrypoint: `python stage-4/app.py`
  - Binds to `0.0.0.0:8080` (or dynamic `$PORT`).
  - Serving the complete interactive reservation Webview: `/` (home grid), `/signup`, `/login`, `/lookup`, and `/health`.
  - Complete operational instructions documented in [`docs/replit_deployment.md`](replit_deployment.md).

---

## 12. Presentation & Video Status

- **Video Demo Requirement**:
  - Demonstrates Band room operation, agent handoffs, reviewer rejection/repair loop, and live application UI.
- **Presentation / Slides Requirement**:
  - Focuses on genuine factory architecture, autonomy metrics ($25.95 spend, 55.7 min active time), independent review value, and failure recovery.
- External submission links are populated directly on the hackathon submission portal.

---

## 13. Remaining Risks & Disclosure Boundaries

To remain 100% truthful, compliant, and defensible before hackathon judges, our team **MUST ADHERE** to the following disclosure boundaries:

1. **DO NOT claim "Zero Human Intervention" for the entire run**:
   - Truth: Stage 1 ran from dispatch to approval with **zero human intervention**.
   - Stages 2–4 required two administrative process-resume messages following API rate-limit and socket drop pauses. Neither message contained technical advice, code, or hints.
2. **DO NOT claim the judged run used the Gemini coordinator**:
   - Truth: The factory supports Gemini and includes rate-limiting adapters and workspace tools, but the judged run used the all-Claude lineup (`claude-sonnet-5-5` coordinator, `claude-opus-5-5` builder and reviewer) because no Gemini key was available at dispatch.
3. **DO NOT alter stage application code or Git history**:
   - All stage application code and commit SHAs must remain identical to what was generated by the Band agents.

---

## 14. Final Pre-Submission Checklist

- [x] Working branch is `main`, fully pushed to GitHub.
- [x] All 13 stage commits were authored exclusively by `Implementer <implementer@factory.local>`.
- [x] Zero stage application files were altered after the Band session ended.
- [x] `room.json` is the full unpruned session download (`scope: full`).
- [x] Credential scan passes with 0 leaks in `room.json` or tracked files.
- [x] Mandates match the actual judged lineup and contain zero track vocabulary.
- [x] Gates 1, 2, and 4 are completely verified and pass.
- [x] Replit deployment files are in place and decoupled from judged code.
- [x] All relative markdown links resolve correctly.
- [x] README and FACTORY.md honestly disclose spend, timing, models, and resume messages.

**Final Recommendation**: **PROCEED TO SUBMISSION**. The repository is completely compliant, authentic, and judge-ready.
