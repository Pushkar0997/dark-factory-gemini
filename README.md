# 🏭 Gemini Dark Factory — Autonomous Multi-Agent Software Factory

> An autonomous, three-seat software engineering factory powered by Google Gemini and [BAND Desktop](https://band.ai), prepared for the **[WeAreDevelopers x BAND: Dark Factory Hackathon](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)**.

---

## 1. What This Project Is

This repository contains the software factory configuration, seat mandates, and stage scaffolding for the **WeAreDevelopers × BAND Dark Factory Hackathon**.

The objective of a Dark Factory is to build a self-operating software factory inside Band Desktop: a band of coding agents that plans work, implements it, hands off evidence, and independently validates its own output. Once the human operator dispatches a stage specification into the Band room, the factory operates with **zero human intervention** until completion.

---

## 2. The Three-Seat Factory Architecture

The factory partitions software engineering responsibilities across three distinct seats:

```
                  ┌──────────────────────┐
                  │    Human Operator    │
                  └──────────┬───────────┘
                             │ (Task Dispatch)
                             ▼
                  ┌──────────────────────┐
                  │   @Planner (Seat 1)  │
                  └──────────┬───────────┘
                             │ (Self-Contained Assignment)
                             ▼
                  ┌──────────────────────┐
                  │   @Builder (Seat 2)  │
                  └──────────┬───────────┘
                             │ (Commit Hash + Evidence)
                             ▼
                  ┌──────────────────────┐
                  │  @Reviewer (Seat 3)  │
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼ (Defect Report)                 ▼ (Verification Approval)
     [@Builder remediates]            [@Planner advances stage]
```

### Seat Ownership & Roles
- **📋 Planner (`mandates/planner.md` / `factory/planner.py`)**:
  - **Owns**: Requirements decomposition, milestone planning, task dispatch, dependency ordering, and stage progression.
  - **Constraint**: Never writes application source code directly.
- **🔨 Builder (`mandates/builder.md` / `factory/builder.py`)**:
  - **Owns**: Implementation of features, Docker containerization, `RUN.md` documentation, local verification, and atomic Git commits.
  - **Constraint**: Never unilaterally approves its own work.
- **🔍 Reviewer (`mandates/reviewer.md` / `factory/reviewer.py`)**:
  - **Owns**: Independent verification on clean checkouts, automated test suite execution, specification auditing, and defect reporting.
  - **Constraint**: Never patches implementation code directly; reports reproduction steps back to the Builder.

---

## 3. Repository Organization

```text
dark-factory-gemini/
├── README.md               # Project overview, architecture, and operator manual
├── FACTORY.md              # Generic factory specification, protocols, and design choices
├── pyproject.toml          # Project dependencies and script entry points
├── uv.lock                 # Pinned dependencies lockfile
├── .gitignore              # Git ignore rules ensuring zero credential tracking
├── .env.example            # Environment variable template
├── agent_config.yaml.example # Band agent seat credentials template
│
├── mandates/               # One generic mandate per seat (Gate 1 compliant)
│   ├── planner.md          # Planner mandate (Harness: Google ADK, Model: gemini-3.8-flash)
│   ├── builder.md          # Builder mandate (Harness: Google ADK, Model: gemini-3.8-flash)
│   └── reviewer.md         # Reviewer mandate (Harness: Google ADK, Model: gemini-3.8-flash-lite)
│
├── factory/                # Reusable factory runtime components
│   ├── __init__.py         # Package exports
│   ├── config.py           # Centralized model registry and seat prompt definitions
│   └── adapter.py          # Google ADK adapter initialization and runner logic
│
├── stage-1/                # Stage 1 workspace (Dockerfile, RUN.md, source)
├── stage-2/                # Stage 2 workspace (Stage 1 carried forward + Browser UI)
├── stage-3/                # Stage 3 workspace (Stage 2 carried forward + Temporal rules)
├── stage-4/                # Stage 4 workspace (Stage 3 carried forward + Batch operations)
│
├── scripts/                # Verification and operational helpers
│   ├── run_checks.py       # Offline submission integrity scanner
│   └── export_room_guide.md# Guide for exporting and auditing room.json
│
└── docs/                   # Engineering documentation
    ├── architecture.md     # In-depth architectural sequence flows and state models
    ├── decisions.md        # Track recommendation (Tablekeeper) and design choices
    └── progress.md         # Truthful project progress and gate status tracker
```

---

## 4. Local Setup & Running the Factory

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker daemon running locally
- A [BAND Desktop](https://band.ai) account with three pre-configured agent seats
- A [Google AI API Key](https://aistudio.google.com/apikey)

### Configuration

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Pushkar0997/dark-factory-gemini.git
   cd dark-factory-gemini
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Configure local credentials** (kept outside Git):
   ```bash
   cp .env.example .env
   cp agent_config.yaml.example agent_config.yaml
   ```
   Edit `.env` with your `GOOGLE_API_KEY`, and update `agent_config.yaml` with your three Band agent IDs and keys.

### Starting the Factory Seats

Start each agent in a separate terminal:

```bash
# Terminal 1: Planner
uv run python planner.py

# Terminal 2: Builder
uv run python builder.py

# Terminal 3: Reviewer
uv run python reviewer.py
```

Each seat supports custom model selection via the `--model` flag:
```bash
uv run python planner.py --model gemini-3.8-flash
```

---

## 5. Verification & Submission Integrity

### Validating Repository Structure
Run the submission readiness check:
```bash
python scripts/run_checks.py
```

If the official hackathon harness is available:
```bash
python -m harness check . --track tablekeeper
```

### Room Evidence (`room.json`)
The `room.json` file is exported directly from the Band console after the live run. It provides immutable cryptographic proof that the service was generated through multi-agent collaboration rather than human authoring.
See [`scripts/export_room_guide.md`](file:///d:/Coding_Work/dark-factory-gemini/scripts/export_room_guide.md) for export instructions.

---

## 6. Current Implementation Status

In adherence to hackathon integrity rules, this repository strictly separates implemented groundwork from ungenerated stage outputs:

| Component | Status | Description |
|---|---|---|
| **Factory Architecture & Runtime** | `IMPLEMENTED` | Centralized config, Google ADK adapters, and runner scripts. |
| **Mandates** | `VERIFIED` | Three generic mandates declaring exact Harness and Model values (zero track vocabulary). |
| **Documentation & Decisions** | `VERIFIED` | Comprehensive `FACTORY.md`, architecture docs, and track evaluation. |
| **Stage Scaffolding** | `PLACEHOLDER` | `stage-1/` through `stage-4/` contain build contracts. Implementation code will be generated during the live Band session. |
| **Session Log (`room.json`)** | `PENDING LIVE RUN` | Will be downloaded from Band console upon completing the live factory run. |
| **Service Implementation** | `PENDING LIVE RUN` | Zero hand-built code committed. |
