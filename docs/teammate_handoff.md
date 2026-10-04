# 🤝 Teammate Handoff & Operator Manual

**Target Audience**: Any engineer taking over the Gemini Dark Factory project.  
**Hackathon**: [WeAreDevelopers × BAND: Dark Factory Hackathon](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)  
**Track Recommendation**: `tablekeeper` (see rationale in [`docs/decisions.md`](file:///d:/Coding_Work/dark-factory-gemini/docs/decisions.md))  

---

## 1. Executive Summary & Current State

The foundation of the factory is **complete, verified offline, and strictly compliant** with the official hackathon rules. 

We have deliberately avoided shortcuts:
- **No fake code**: We have **NOT** pre-written application code in `stage-1/` through `stage-4/`. The hackathon requires all implementation code to be created autonomously by the agents during the live room session.
- **No synthetic evidence**: We have **NOT** fabricated `room.json`. That file must come directly from your live Band Desktop room export.
- **No model spoofing**: We do not silently switch models under rate limits. The declared models in `mandates/` match `factory/config.py` and are preserved during retries.

### What Has Already Been Completed
1. **Repository Architecture & Packaging**:
   - `pyproject.toml` with `uv` workspace integration and Hatchling package configuration (`factory`).
   - CLI entrypoints: `factory-planner`, `factory-builder`, `factory-reviewer` as well as root-level wrappers (`planner.py`, `builder.py`, `reviewer.py`).
2. **Resilient Google ADK Adapter (`factory/adapter.py`)**:
   - Custom `ResilientGoogleADKAdapter` subclassing `GoogleADKAdapter`.
   - Built-in inter-turn pacing throttle (`FACTORY_TURN_DELAY`) to avoid burst rate limits.
   - Exponential backoff with random jitter on HTTP 429 (`ResourceExhausted`) and 503 errors.
   - Guarantees that the declared model identity (`gemini-3.8-flash` / `gemini-3.8-flash-lite`) is strictly preserved across all retries.
3. **Mandates (`mandates/`)**:
   - Fully generic operational mandates for `@Planner`, `@Builder`, and `@Reviewer`.
   - Verified 100% clean of all track vocabulary tokens (Gate 4 compliant).
   - Required `Harness: Google ADK` and `Model: gemini-...` headers declared (Gate 1 compliant).
   - Compatibility aliases (`geminiplanner.md`, `geminibuilder.md`, `geminireviewer.md`) provided for flexible Band Desktop naming.
4. **Stage Scaffolding (`stage-1/` through `stage-4/`)**:
   - Clean, honest container contracts: each stage directory has a valid `Dockerfile` and `RUN.md` specifying execution commands, port bindings (`8080`), and environment requirements.
5. **Verification & Audit Tooling**:
   - `scripts/run_checks.py`: Comprehensive offline integrity scanner mirroring the official `harness check`.
   - `scripts/export_room_guide.md`: Step-by-step room evidence export guide.

---

## 2. Important Files to Understand First

Read these files in the following order before starting any live runs:

1. [`FACTORY.md`](file:///d:/Coding_Work/dark-factory-gemini/FACTORY.md):
   - The foundational design specification of our dark factory. Explains the three-seat separation of concerns, the Git commit-based handoff protocol, and evidence verification.
2. [`README.md`](file:///d:/Coding_Work/dark-factory-gemini/README.md):
   - High-level project overview, CLI invocation instructions, and setup guide.
3. [`factory/config.py`](file:///d:/Coding_Work/dark-factory-gemini/factory/config.py):
   - Central model definitions (`DEFAULT_PLANNER_MODEL`, `DEFAULT_BUILDER_MODEL`, `DEFAULT_REVIEWER_MODEL`), seat prompts, and seat definitions.
4. [`factory/adapter.py`](file:///d:/Coding_Work/dark-factory-gemini/factory/adapter.py):
   - Rate-limit handling, turn pacing, and `ResilientGoogleADKAdapter` implementation.
5. [`mandates/README.md`](file:///d:/Coding_Work/dark-factory-gemini/mandates/README.md):
   - Explains how Band Desktop agent names map to mandate filenames via the harness slug rule.
6. [`docs/decisions.md`](file:///d:/Coding_Work/dark-factory-gemini/docs/decisions.md):
   - Strategic analysis of `tablekeeper` vs `pocketful`, model allocation strategy, and risk mitigations.

---

## 3. What NOT to Change Unnecessarily

To prevent accidental gate disqualifications:

- ❌ **DO NOT touch the model declarations in `mandates/*.md`** without simultaneously updating `factory/config.py`. They must match exactly.
- ❌ **DO NOT add track-specific words** (like `booking`, `table`, `seat`, `ledger`, `split`, etc.) to any file in `mandates/` or any prompt in `factory/config.py`. Gate 4 will automatically disqualify the repository if track terms appear in mandates.
- ❌ **DO NOT write application code in `stage-1/` through `stage-4/` manually**. That code must be authored by the agents running inside Band Desktop.
- ❌ **DO NOT commit `.env` or `agent_config.yaml` to Git**. They are listed in `.gitignore` and must remain private.
- ❌ **DO NOT enable `--allow-fallback` during the official competition run**. Strict mode preserves the declared model identity required by Gate 1.

---

## 4. Rate-Limit Configuration & Tuning

When running multiple Gemini agents concurrently on free-tier API keys, Google enforces strict rate limits (RPM and TPM). Our `ResilientGoogleADKAdapter` manages this automatically, but you can tune parameters in your `.env` file if needed:

| Environment Variable | Default | Purpose |
|---|---|---|
| `FACTORY_TURN_DELAY` | `1.5` | Minimum seconds to wait between consecutive turns to prevent burst requests. |
| `FACTORY_MAX_RETRIES` | `5` | Maximum retry attempts when a 429 / 503 / ResourceExhausted occurs. |
| `FACTORY_INITIAL_BACKOFF` | `4.0` | Initial backoff delay (seconds) before the first retry attempt. |
| `FACTORY_MAX_BACKOFF` | `60.0` | Ceiling delay cap for exponential backoff. |

If you observe frequent 429 logs in your terminals:
- Increase `FACTORY_TURN_DELAY` to `3.0` or `5.0`.
- Increase `FACTORY_INITIAL_BACKOFF` to `6.0`.
- Let the adapter sleep and recover automatically; **do not interrupt the agent process**.

---

## 5. Step-by-Step Execution Plan

Follow these exact steps to complete the hackathon run:

### Step 1: Local Environment Preparation
1. Ensure Python 3.13+ and `uv` are installed.
2. Ensure Docker Desktop is running locally (`docker info`).
3. Set up local configuration files:
   ```bash
   cp .env.example .env
   cp agent_config.yaml.example agent_config.yaml
   ```
4. Put your Google Gemini API key into `.env`:
   ```bash
   GOOGLE_API_KEY="AIzaSy..."
   ```

### Step 2: BAND Desktop Setup & Seat Registration
1. Launch **BAND Desktop**.
2. Create or verify 3 agent seats with the following display names:
   - **`Planner`**
   - **`Builder`**
   - **`Reviewer`**
3. Copy each agent's **Agent ID** and **API Key** from BAND Desktop into `agent_config.yaml`:
   ```yaml
   gemini_planner:
     agent_id: "0f0720eb-..."
     api_key: "band_key_..."
   gemini_builder:
     agent_id: "1a2b3c4d-..."
     api_key: "band_key_..."
   gemini_reviewer:
     agent_id: "5e6f7a8b-..."
     api_key: "band_key_..."
   ```
4. Create a Band room (e.g. `dark-factory-rehearsal` for practice, or `dark-factory-tablekeeper` for the real run).
5. Invite all 3 agents into the room.

### Step 3: Run the Toy Track Rehearsal (Dry Run)
Before doing the real competition run, execute a quick rehearsal on the Toy track to ensure multi-agent communication and handle mentions work end-to-end:

1. Open 3 separate terminal tabs:
   ```bash
   # Terminal 1:
   uv run python planner.py

   # Terminal 2:
   uv run python builder.py

   # Terminal 3:
   uv run python reviewer.py
   ```
2. Verify all three agents show `Connected to platform` and are listening.
3. In BAND Desktop, send the kickoff prompt in the room addressing `@Planner`:
   ```text
   @Planner Begin factory operation for the Toy track.
   Implement a minimal HTTP service on port 8080 that returns 200 OK with {"status": "ok"} at /healthz.
   Coordinate with @Builder to implement in stage-1/ and @Reviewer to verify.
   Operate with full autonomy.
   ```
4. Observe the room:
   - Check that `@Planner` addresses `@Builder`.
   - Check that `@Builder` implements the code and addresses `@Reviewer`.
   - Check that `@Reviewer` runs tests and reports back to `@Planner` and `@Builder`.
   - Ensure handle mentions (`@[[participant-id]]`) are exchanged in both directions (Gate 2 requirement).
5. Export the test session from Band Desktop to verify the export process.

### Step 4: The Official Competition Run (`tablekeeper`)
Once the rehearsal confirms communication and tooling:

1. Create a fresh Band room named **`tablekeeper-factory`**.
2. Invite `Planner`, `Builder`, and `Reviewer`.
3. In separate terminals, ensure all 3 agent processes are running:
   ```bash
   uv run python planner.py
   uv run python builder.py
   uv run python reviewer.py
   ```
4. **Dispatch Stage 1**:
   Copy the specification from [`tablekeeper/spec/stage-1.md`](https://github.com/band-ai/dark-factory-wearedevs/blob/main/tablekeeper/spec/stage-1.md) and paste it into the room addressing `@Planner`:
   ```text
   @Planner Begin autonomous dark factory operation for Tablekeeper Stage 1.
   Here is the complete specification:
   [PASTE STAGE-1.MD CONTENT HERE]
   Decompose the requirements, direct @Builder to implement in stage-1/, and direct @Reviewer to independently verify.
   Do not ask for human input. Advance stages upon verified approval.
   ```
5. **Monitor Without Intervening**:
   - Let the agents execute their plan, create the Dockerfile, write source files, execute test suites, and review.
   - If the Reviewer reports defects, the Builder will remediate them.
   - When Stage 1 is approved, dispatch Stage 2 (or have the Planner carry forward from the verified baseline).
   - Repeat through Stage 4.

### Step 5: Exporting Evidence (`room.json`)
Immediately after completing the factory run:
1. In BAND Desktop, open the room settings / menu.
2. Select **"Download full session"** (do NOT choose filtered).
3. Save the exported JSON file directly to the root of this repository as:
   ```text
   dark-factory-gemini/room.json
   ```
4. Check that `room.json` contains the full message history and tool calls.

### Step 6: Final Pre-Submission Validation
Run the submission readiness scanner:
```bash
uv run python scripts/run_checks.py tablekeeper
```

If the official hackathon harness repo is available locally:
```bash
python -m harness check . --track tablekeeper
```

All gates must pass:
- [x] **Gate 1**: Three mandates with valid `Harness` and `Model` declarations matching room seats.
- [x] **Gate 2**: Two seats exchanged messages using handles in both directions.
- [x] **Gate 3**: Stage directories exist with `Dockerfile` and `RUN.md`.
- [x] **Gate 4**: Zero track vocabulary leakage in `mandates/`.
- [x] **Gate 5**: Zero committed credentials or API keys.

### Step 7: Commit & Push to GitHub
```bash
git add stage-1 stage-2 stage-3 stage-4 room.json
git status  # Double-check that .env and agent_config.yaml are NOT staged!
git commit -m "feat(submission): autonomous tablekeeper multi-agent factory run and room evidence"
git push origin main
```

Submit the GitHub repository URL (`https://github.com/Pushkar0997/dark-factory-gemini`) to the hackathon submission portal on LabLab.ai.
