# dark-factory-gemini

A generic **coordinator → implementer → reviewer** software factory for
[Band Desktop](https://band.ai), entered in the WeAreDevelopers × BAND *Dark Factory*
hackathon on the **`tablekeeper`** track.

Seats can run on **Claude Code** (Band Desktop runtimes), **Google ADK / Gemini** (this repo's
`factory-seat` runner, with sandboxed workspace tools), or a mix. The submitted lineup is
**hybrid**: a Gemini coordinator with Claude Code implementer and reviewer.

| Read | For |
|---|---|
| [FACTORY.md](FACTORY.md) | how the factory works, how to stand it up, costs, failure handling |
| [mandates/](mandates/) | one mandate per seat, generic, with its harness and model |
| [docs/teammate_handoff.md](docs/teammate_handoff.md) | current status, exact commands, run book |
| [docs/decisions.md](docs/decisions.md) | track choice and other decisions, with evidence |
| [docs/track-plan.md](docs/track-plan.md) | what each tablekeeper stage demands, and what reviewers must probe |
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

## Team

Pushkar Kumar, Amaan Sayyed.
