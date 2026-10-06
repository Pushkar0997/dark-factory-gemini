# dark-factory-gemini

A generic **coordinator → implementer → reviewer** software factory for
[Band Desktop](https://band.ai), entered in the WeAreDevelopers × BAND *Dark Factory*
hackathon on the **`tablekeeper`** track.

🌐 **Live Demo (Stage 4 Tablekeeper)**: **[https://tablekeeper-demo-rxjp.onrender.com](https://tablekeeper-demo-rxjp.onrender.com)**  
*Live, interactive autonomous Stage 4 reservation service running directly from the Band-generated artifact.*

Seats can run on **Claude Code** (Band Desktop runtimes), **Google ADK / Gemini** (this repo's
`factory-seat` runner, with sandboxed workspace tools), or a mix. The judged run used the
**claude** lineup (no Gemini key was available at dispatch); **hybrid** (Gemini coordinator +
Claude Code implementer/reviewer) is the recommended lineup when a Gemini key is present.

## Result

From **one dispatch**, the three seats built and approved **all four tablekeeper stages**.
The official harness in isolated (judging) mode passes every shipped check, and every folder
claims its own stage: suite 1 120/120, suite 2 25/25, suite 3 7/7, suite 4 6/6.

- **Review that changed the code:** stage 1 was rejected with three defects the shipped
  checks never caught. They were fixed and re-verified in about 4 minutes. Two later review
  notes became fixes in the next stage.
- **Time and spend:** 55.7 min of active work and **$25.95** at list prices. Wall time was
  9 h 35 min, because two usage limits and one network outage left the band idle.
- **Disclosure:** two human "resume" messages were posted after the dispatch (administrative
  process-resume messages following API rate-limit and socket drop pauses, with zero technical
  hints or code edits). They are quoted exactly in [FACTORY.md §11](FACTORY.md#11-measurements-and-results).
  Stage 1 ran with zero human intervention from dispatch to approval.

| Read | For |
|---|---|
| [FACTORY.md](FACTORY.md) | how the factory works, how to stand it up, costs, failure handling |
| [mandates/](mandates/) | one mandate per seat, generic, with its harness and model |
| [docs/final_compliance_audit.md](docs/final_compliance_audit.md) | complete hackathon-rule compliance audit and evidence trail |
| [docs/teammate_handoff.md](docs/teammate_handoff.md) | current status, exact commands, run book |
| [docs/decisions.md](docs/decisions.md) | track choice and other decisions, with evidence |
| `stage-1/` … `stage-4/`, `room.json` | **produced by the band** in the judged run and merged in; never hand-written |

## Layout

```
factory/                 runtime + configuration
  mandate_templates/     generic role texts (coordinator, implementer, reviewer)
  lineups.toml           which Band seat plays which role, on which harness/model
  lineup.py              lineup loading + mandate rendering
  seat.py                `factory-seat`: runs a Google ADK seat from its mandate
  adapter.py             rate-limit-resilient Google ADK adapter
  workspace_tools.py     sandboxed read/list/write/run tools for Gemini seats
  config.py              retry/pacing knobs (env-tunable), model candidates
scripts/
  render_mandates.py     lineup → mandates/
  apply_lineup.py        pin model + instructions on Band Desktop Claude Code seats
  prepare_run.sh         fresh result repo + seat config + dispatch text for a run
  run_checks.py          self-checks + official `harness check` / `harness run`
  room_precheck.py       preview gates 1-2 on a live room before the room.json download
  import_room.sh         room download → room.json, unchanged, credential-scanned, committed
  assemble_submission.sh merge the band's result repo history into this repo
  fresh_clone_check.sh   the guide's pre-submission checks on a fresh clone
tests/                   unit tests for the factory's own logic
```

## Quick start

```bash
uv sync
uv run python scripts/run_checks.py        # factory self-checks
```

Full setup, the toy rehearsal and the real run: [docs/teammate_handoff.md](docs/teammate_handoff.md).

## Public Live Demo (Stage 4 Tablekeeper)

The autonomous **Stage 4 Tablekeeper** application is publicly accessible and running live at:

👉 **[https://tablekeeper-demo-rxjp.onrender.com](https://tablekeeper-demo-rxjp.onrender.com)**

### Key Routes & Interactive Webview

| Route | Method | Description |
|---|---|---|
| `/` | `GET` | Main Tablekeeper browser UI (reservation screen & restaurant selector) |
| `/signup` | `GET` | User account registration interface |
| `/login` | `GET` | Authentication interface |
| `/lookup` | `GET` | Reservation reference code lookup screen |
| `/health` | `GET` | Service status probe (returns `{"status": "ok"}`) |
| `/restaurants` | `GET` | Seeded restaurant catalog API (`r_anker`, `r_two`) |
| `/availability` | `GET` | Real-time table slot availability query API |
| `/static/app.css`, `app.js` | `GET` | Bundled styling and frontend application assets |

> **Competition Integrity Note:** The public web demo is purely a presentation layer. The official competition Docker artifacts (`stage-4/Dockerfile`, `stage-4/RUN.md`), Band session logs (`room.json`), and stage directories remain the immutable source of truth.

### Alternative Deployment Options

- **Docker (Competition Reference)**:
  ```bash
  cd stage-4 && docker build -t tablekeeper-s4 . && docker run -p 8080:8080 tablekeeper-s4
  ```
- **Replit (Optional One-Click Import)**:
  The repository includes optional Replit configuration (`.replit`, `replit.nix`, `requirements.txt`). To self-host on Replit, import `https://github.com/Pushkar0997/dark-factory-gemini` into Replit and click **Run**. Detailed instructions: [docs/replit_deployment.md](docs/replit_deployment.md).

## Team

Pushkar Kumar, Amaan Sayyed.


