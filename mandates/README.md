# Factory Seat Mandates (`mandates/`)

This directory contains the operational mandates for each seat in the Gemini Dark Factory.

---

## Mandate Compliance & The Slug-Matching Rule

Under the official Hackathon submission rules ([Gate 1 & Gate 4](https://github.com/band-ai/dark-factory-wearedevs)), mandate files are audited automatically by `harness check`:

1. **Gate 1 (Harness & Model Declaration)**:
   - Each mandate file must explicitly declare which harness and model the seat runs:
     ```markdown
     Harness: Google ADK
     Model: gemini-3.8-flash
     ```
   - The declared model must match the model actually utilized during the autonomous run.

2. **Gate 1 (Seat-to-File Slug Resolution)**:
   - When `room.json` is exported from BAND Desktop, each message contains a `senderName` attribute.
   - The harness extracts the unique set of agent `senderName`s and computes an alphanumeric slug:
     ```python
     def _slug(text: str) -> str:
         return re.sub(r"[^a-z0-9]", "", str(text).lower())
     ```
   - For every distinct agent name in the room, the harness asserts that `mandates/{_slug(name)}.md` exists.

3. **Gate 4 (Factory Generality / Zero Track Tokens)**:
   - Mandate files must describe **how the factory operates**, never the target problem.
   - Mandates must contain **zero vocabulary tokens** from the competition tracks (e.g. Tablekeeper or Pocketful).

---

## Canonical Mandates vs. Display Name Aliases

Depending on how an operator registers agent seats inside the BAND Desktop application:

| Band Desktop Agent Name | Computed Slug | Corresponding Mandate File | Role |
|---|---|---|---|
| `Planner` | `planner` | [`mandates/planner.md`](file:///d:/Coding_Work/dark-factory-gemini/mandates/planner.md) | Canonical Planner |
| `Builder` | `builder` | [`mandates/builder.md`](file:///d:/Coding_Work/dark-factory-gemini/mandates/builder.md) | Canonical Builder |
| `Reviewer` | `reviewer` | [`mandates/reviewer.md`](file:///d:/Coding_Work/dark-factory-gemini/mandates/reviewer.md) | Canonical Reviewer |
| `GeminiPlanner` | `geminiplanner` | [`mandates/geminiplanner.md`](file:///d:/Coding_Work/dark-factory-gemini/mandates/geminiplanner.md) | Compatibility Alias |
| `GeminiBuilder` | `geminibuilder` | [`mandates/geminibuilder.md`](file:///d:/Coding_Work/dark-factory-gemini/mandates/geminibuilder.md) | Compatibility Alias |
| `GeminiReviewer` | `geminireviewer` | [`mandates/geminireviewer.md`](file:///d:/Coding_Work/dark-factory-gemini/mandates/geminireviewer.md) | Compatibility Alias |

> [!TIP]
> **Operator Recommendation**: When creating agent seats in BAND Desktop for the competition room, name them `Planner`, `Builder`, and `Reviewer`. This simplifies mention handles (`@Planner`, `@Builder`, `@Reviewer`) and aligns with the canonical mandate files. The `gemini*.md` aliases are maintained to ensure 100% harness pass rates regardless of whether the prefix is used.

All six files in this directory are 100% compliant:
- Verified clean of all competition track vocabulary against official `vocabulary.py`.
- Formatted with required `Harness: Google ADK` and `Model: gemini-...` headers.
