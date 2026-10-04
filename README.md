# 🏭 Gemini Dark Factory — Autonomous Multi-Agent Software Factory

> An autonomous, three-seat software engineering factory powered by Google Gemini and [BAND Desktop](https://band.ai), prepared for the **[WeAreDevelopers x BAND: Dark Factory Hackathon](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)**.

---

## 1. Executive Summary

This repository contains the software factory configuration, seat mandates, resilient Google ADK adapter, and stage scaffolding for the **WeAreDevelopers × BAND Dark Factory Hackathon**.

The objective of a Dark Factory is to build a self-operating software factory inside Band Desktop: a team of autonomous AI coding agents that ingests requirements, decomposes tasks, writes code, containerizes services, executes test suites, and independently validates its own output. Once the human operator dispatches a stage specification into the Band room, the factory operates with **zero human intervention**.

### 🌟 Project Status at a Glance

| Component | Status | Location / Details |
|---|---|---|
| **Factory Runtime Architecture** | `COMPLETED` | Modular package in [`factory/`](file:///d:/Coding_Work/dark-factory-gemini/factory), centralized config, CLI entrypoints. |
| **Resilient ADK Adapter** | `COMPLETED` | [`factory/adapter.py`](file:///d:/Coding_Work/dark-factory-gemini/factory/adapter.py): Exponential backoff, jitter, turn pacing, strictly preserves model identity. |
| **Mandates (Gate 1 & Gate 4)** | `VERIFIED` | [`mandates/`](file:///d:/Coding_Work/dark-factory-gemini/mandates): Declares exact Harness & Model, 100% clean of track vocabulary. |
| **Stage Scaffolding** | `VERIFIED` | [`stage-1/` through `stage-4/`](file:///d:/Coding_Work/dark-factory-gemini): Container contracts (`Dockerfile`, `RUN.md`). |
| **Integrity & Audit Tooling** | `COMPLETED` | [`scripts/run_checks.py`](file:///d:/Coding_Work/dark-factory-gemini/scripts/run_checks.py): Offline scanner mirroring official `harness check`. |
| **Documentation & Handoff** | `COMPLETED` | [`FACTORY.md`](file:///d:/Coding_Work/dark-factory-gemini/FACTORY.md), [`docs/teammate_handoff.md`](file:///d:/Coding_Work/dark-factory-gemini/docs/teammate_handoff.md), [`docs/decisions.md`](file:///d:/Coding_Work/dark-factory-gemini/docs/decisions.md). |
| **Application Source Code** | `PENDING LIVE RUN` | **Zero fake code committed**. Code must be generated autonomously by agents in Band Desktop. |
| **Room Session Evidence** | `PENDING LIVE RUN` | `room.json` must be exported directly from Band Desktop after the autonomous run. |

---

## 2. The Three-Seat Factory Architecture

The factory partitions software engineering responsibilities across three specialized seats:

```
                  ┌─────────────────────────────────┐
                  │          Human Operator         │
                  └────────────────┬────────────────┘
                                   │ (Kickoff Specification)
                                   ▼
                  ┌─────────────────────────────────┐
                  │        @Planner (Seat 1)        │
                  │     Harness: Google ADK         │
                  │    Model: gemini-3.8-flash      │
                  └────────────────┬────────────────┘
                                   │ (Self-Contained Task Assignment)
                                   ▼
                  ┌─────────────────────────────────┐
                  │        @Builder (Seat 2)        │
                  │     Harness: Google ADK         │
                  │    Model: gemini-3.8-flash      │
                  └────────────────┬────────────────┘
                                   │ (Commit Hash + Execution Proof)
                                   ▼
                  ┌─────────────────────────────────┐
                  │       @Reviewer (Seat 3)        │
                  │     Harness: Google ADK         │
                  │  Model: gemini-3.8-flash-lite   │
                  └────────────────┬────────────────┘
                                   │
             ┌─────────────────────┴─────────────────────┐
             ▼ (Defect Report)                           ▼ (Approval & Passing Tests)
   [@Builder remediates]                         [@Planner advances stage]
```

### Seat Roles & Responsibilities

1. **📋 Planner (`mandates/planner.md` / `factory/planner.py`)**:
   - **Owns**: Requirements decomposition, milestone planning, dependency sequencing, task dispatch, and stage progression.
   - **Constraint**: Never writes application source code directly.
2. **🔨 Builder (`mandates/builder.md` / `factory/builder.py`)**:
   - **Owns**: Implementation of features, Docker containerization, `RUN.md` documentation, local verification, and atomic Git commits.
   - **Constraint**: Never unilaterally approves its own work.
3. **🔍 Reviewer (`mandates/reviewer.md` / `factory/reviewer.py`)**:
   - **Owns**: Independent verification on clean checkouts, automated test suite execution, specification auditing, and defect reporting.
   - **Constraint**: Never patches implementation code directly; reports reproduction steps back to the Builder.

---

## 3. Resilient Rate-Limit & Backoff Strategy

During rapid multi-agent collaboration, Gemini free-tier quotas can encounter HTTP `429 Too Many Requests` (`RESOURCE_EXHAUSTED`) or `503 Service Unavailable` errors.

To solve this **without violating Gate 1 model declarations**, we implemented `ResilientGoogleADKAdapter` in [`factory/adapter.py`](file:///d:/Coding_Work/dark-factory-gemini/factory/adapter.py):

### Key Mechanisms:
- **Strict Model Preservation**: Retries never substitute or silently downgrade the declared model (`gemini-3.8-flash` / `gemini-3.8-flash-lite`).
- **Turn Pacing Throttle**: Enforces a minimum delay (`FACTORY_TURN_DELAY`, default `1.5s`) between consecutive turns for an agent, dampening burst traffic.
- **Exponential Backoff with Random Jitter**:
  $$\text{Delay} = \min(\text{max\_backoff}, \text{initial\_backoff} \times 2^{\text{attempt}-1}) + \text{jitter}$$
  Defaults: 5 attempts, initial 4.0s backoff, 2.0s random jitter. Jitter prevents multiple seats from colliding in synchronized retry waves.
- **Pre-Failure Interception**: Transient errors are caught before Band's `tools.send_failure()` is triggered, preventing the Band platform from prematurely dropping or skipping turns.
- **Configurability**: All parameters can be tuned in `.env` without modifying Python code.

---

## 4. Repository Layout

```text
dark-factory-gemini/
├── README.md                 # Project overview, architecture, and operator guide
├── FACTORY.md                # Generic factory specification, protocols, and design choices
├── pyproject.toml            # Project dependencies and script entry points
├── uv.lock                   # Pinned dependency lockfile
├── .gitignore                # Git ignore rules ensuring zero credential tracking
├── .env.example              # Environment variable template
├── agent_config.yaml.example # Band agent seat credentials template
│
├── mandates/                 # Operational mandates per seat (Gate 1 & Gate 4 compliant)
│   ├── README.md             # Mandate compliance & harness slug-matching documentation
│   ├── planner.md            # Canonical Planner mandate (Google ADK / gemini-3.8-flash)
│   ├── builder.md            # Canonical Builder mandate (Google ADK / gemini-3.8-flash)
│   ├── reviewer.md           # Canonical Reviewer mandate (Google ADK / gemini-3.8-flash-lite)
│   ├── geminiplanner.md      # Compatibility alias for Band Desktop "GeminiPlanner"
│   ├── geminibuilder.md      # Compatibility alias for Band Desktop "GeminiBuilder"
│   └── geminireviewer.md     # Compatibility alias for Band Desktop "GeminiReviewer"
│
├── factory/                  # Modular factory runtime package
│   ├── __init__.py           # Package exports
│   ├── config.py             # Centralized model registry, seat configs, and system prompts
│   ├── adapter.py            # Resilient Google ADK adapter with backoff & pacing
│   ├── planner.py            # Planner CLI entrypoint
│   ├── builder.py            # Builder CLI entrypoint
│   └── reviewer.py           # Reviewer CLI entrypoint
│
├── stage-1/                  # Stage 1 workspace (Dockerfile, RUN.md contracts)
├── stage-2/                  # Stage 2 workspace (Dockerfile, RUN.md contracts)
├── stage-3/                  # Stage 3 workspace (Dockerfile, RUN.md contracts)
├── stage-4/                  # Stage 4 workspace (Dockerfile, RUN.md contracts)
│
├── scripts/                  # Operational and validation tooling
│   ├── run_checks.py         # Offline submission readiness and secret scanner
│   └── export_room_guide.md  # Step-by-step room session export instructions
│
└── docs/                     # Detailed engineering documentation
    ├── teammate_handoff.md   # Actionable manual for the teammate continuing this work
    ├── architecture.md       # In-depth architectural sequence flows and state machines
    ├── decisions.md          # Track evaluation (Tablekeeper vs Pocketful) and strategy
    └── progress.md           # Truthful project progress tracker
```

---

## 5. Local Setup & Running the Factory

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker Desktop running locally
- [BAND Desktop](https://band.ai) installed with 3 agent seats registered
- A [Google AI API Key](https://aistudio.google.com/apikey)

### Configuration

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Pushkar0997/dark-factory-gemini.git
   cd dark-factory-gemini
   ```

2. **Sync dependencies**:
   ```bash
   uv sync
   ```

3. **Configure local credentials** (gitignored):
   ```bash
   cp .env.example .env
   cp agent_config.yaml.example agent_config.yaml
   ```
   - In `.env`: add your `GOOGLE_API_KEY`.
   - In `agent_config.yaml`: add your 3 Band agent IDs and keys.

### Starting the Factory Seats

You can run each seat using either `uv run python <seat>.py` or the packaged CLI script:

```bash
# Terminal 1: Planner
uv run python planner.py
# Or: uv run factory-planner

# Terminal 2: Builder
uv run python builder.py
# Or: uv run factory-builder

# Terminal 3: Reviewer
uv run python reviewer.py
# Or: uv run factory-reviewer
```

---

## 6. Offline Verification

Run our offline submission readiness scanner at any time:

```bash
uv run python scripts/run_checks.py tablekeeper
```

This verifies:
1. All required root files (`README.md`, `FACTORY.md`, `pyproject.toml`) exist.
2. All stage folders (`stage-1/` through `stage-4/`) contain valid `Dockerfile` and `RUN.md`.
3. All mandates in `mandates/` declare valid `Harness:` and `Model:` headers.
4. Mandates contain **zero leaked vocabulary** from the target competition track (Gate 4).
5. No credentials, API keys, or private tokens are tracked by Git (Gate 5).

---

## 7. How to Continue (Next Steps)

For the engineer executing the live run:

👉 **Read [`docs/teammate_handoff.md`](file:///d:/Coding_Work/dark-factory-gemini/docs/teammate_handoff.md)** for exact, step-by-step instructions.

### Summary of Next Actions:
1. **Seat Naming in Band Desktop**: Create 3 seats named `Planner`, `Builder`, and `Reviewer` (matching `@Planner`, `@Builder`, `@Reviewer`).
2. **Execute Toy Rehearsal**: Create a rehearsal room, dispatch a minimal HTTP service task, and confirm multi-agent handle mentions.
3. **Execute Official Run (`tablekeeper`)**: Create room `tablekeeper-factory`, dispatch Stage 1 specification, monitor autonomous progression through Stage 4.
4. **Export `room.json`**: Use **"Download full session"** in Band Desktop and place `room.json` in repository root.
5. **Run Final Verification**: Execute `uv run python scripts/run_checks.py tablekeeper`.
6. **Commit & Push**: Commit the generated stage code and `room.json`, then push to GitHub.
