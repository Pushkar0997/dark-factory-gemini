# Architecture & Strategic Decisions

This document records the foundational architectural decisions made for the Gemini Multi-Agent Factory, including comparative track evaluation, model selection strategies, and compliance guarantees.

---

## 1. Track Evaluation & Recommendation: Tablekeeper vs. Pocketful

### 1.1 Overview of Both Tracks

| Dimension | Tablekeeper (Restaurant Reservation Engine) | Pocketful (Wallet & Settlement Ledger) |
|---|---|---|
| **Core Domain** | Temporal intervals, table seating, cancellation policies, closure replanning | Ledger accounting, idempotent payment transfers, split arithmetic, retroactive adjustments |
| **Stage 1 Scope** | Idempotent bookings, interval collision prevention, atomic multi-reservation moves, export/import | Idempotent transfers, balance invariant conservation (no money created/destroyed/negative), net settlements |
| **Stage 2 Scope** | Browser availability grid, combined-table allocations, stale state recovery | Browser payment feed, holds/captures, split requests, stale state recovery |
| **Stage 3 Scope** | Effective-dated cancellation policies, recurring series with exceptions, truthful history | Immutable payment corrections, historical vs. settlement date views, snapshot pagination |
| **Stage 4 Scope** | Deterministic closure replanning preview and atomic batch application | Refunds from available funds, operator batch corrections across complete settlements |
| **Shipped Check %** | S1: 83%, S2: 41%, S3: 11%, S4: 21% | S1: 79%, S2: 35%, S3: 9%, S4: 16% |

---

### 1.2 Invariant Analysis & Risk Profile

#### Pocketful Risk Profile
- **Financial Conservation Invariant**: Every transaction must strictly conserve seeded money across all wallets. Balances cannot go negative, even transiently.
- **Floating-Point & Rounding Traps**: Split bills must distribute remainders deterministically across minor units (cents). Any deviation immediately invalidates the entire ledger.
- **Race Condition Vulnerability**: Concurrent transfers between mutual wallets can easily trigger deadlocks or transient balance underflows unless strict transaction ordering or lock hierarchy is enforced.
- **Hidden Test Hazard**: Only 9% of Stage 3 checks and 16% of Stage 4 checks are shipped. Subtle ledger accounting edge cases in hold expirations and partial captures are highly likely to fail on hidden judge tests.

#### Tablekeeper Risk Profile
- **Interval Collision Invariant**: Confirmed bookings must never overlap on the same table during the half-open interval `[starts_at, starts_at + duration)`.
- **Relational Alignment**: Interval overlap queries map naturally to standard transactional database constructs (e.g., SQLite with `WHERE table_id = ? AND NOT (ends_at <= ? OR starts_at >= ?)`).
- **Stage 4 Feasibility**: The Stage 4 closure-replanning problem requires a deterministic matching heuristic (preserving as many bookings as possible within capacity rules). While algorithmic, it is self-contained and avoids distributed financial edge cases.
- **Shipped Check Feedback**: Tablekeeper provides higher visibility on shipped checks across every stage (83% vs 79% in Stage 1; 41% vs 35% in Stage 2; 11% vs 9% in Stage 3; 21% vs 16% in Stage 4), giving our automated Reviewer better feedback loops during the live run.

---

### 1.3 Strategic Recommendation: Tablekeeper

**Recommendation: Target the `tablekeeper` track.**

**Rationale**:
1. **Mathematical Cleanliness vs. Financial Traps**: Interval collision math is strictly defined and verifiable via standard range checks. Financial ledger systems have numerous non-obvious traps around hold release timing, retroactive settlement adjustments, and rounding distribution.
2. **Reviewer Testability**: The Reviewer can easily generate synthetic boundary conditions for Tablekeeper (e.g., back-to-back 90-minute bookings at 19:00 and 20:30, adjacent party size constraints, timezone normalization) to probe code robustness beyond the shipped checks.
3. **Multi-Agent Suitability**: Decomposing restaurant tables, combined-table graph allocation (Stage 2), and cancellation cutoff policies (Stage 3) creates clean, well-bounded modules that `@Planner` can delegate to `@Builder` with low ambiguity.

*Note: The factory repository remains strictly track-agnostic. No Tablekeeper-specific code or vocabulary is baked into mandates or factory runtime code.*

---

## 2. Model Selection & Compliance Strategy

### 2.1 The Gate 1 Mandate Challenge
Official Hackathon Eligibility Gate 1 requires:
- Each mandate file in `mandates/` must state the exact `Harness` and `Model` that the seat executes.
- If a factory dynamically falls back to different models at runtime without updating mandates, the declared model differs from the actual model executed in `room.json`, creating an eligibility violation risk.

### 2.2 Centralized Model Architecture
- **Primary Configuration**:
  - Planner: `gemini-3.8-flash`
  - Builder: `gemini-3.8-flash`
  - Reviewer: `gemini-3.8-flash-lite` (or `gemini-3.8-flash`)
- **Strict Mode (Default)**: During judged execution, each agent runs strictly with its assigned model. If the model API is unavailable, the process logs a fatal error rather than silently masking the failure with an undeclared model.
- **Development Fallback Mode**: The `--allow-fallback` CLI flag is available exclusively during iterative testing. If used, any model change must be synchronized back into `mandates/<seat>.md` prior to the official recorded room run.

---

## 3. Separation of Responsibilities

| Invariant | Rationale |
|---|---|
| **Planner does not code** | If the Planner edits code, the system collapses into a single-agent architecture, violating the 25% Agent Teamwork rubric requiring distributed effort. |
| **Builder does not approve** | Self-approval defeats quality assurance. True teamwork requires a distinct verification step that can reject defective work. |
| **Reviewer does not fix** | If the Reviewer applies patches, the defect correction loop is bypassed, leaving no room evidence that feedback changed the outcome. |
