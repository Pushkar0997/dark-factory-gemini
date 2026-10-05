"""Seat lineups: which Band seat plays which factory role, on which harness and model."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINEUPS_FILE = Path(__file__).resolve().parent / "lineups.toml"
TEMPLATES_DIR = Path(__file__).resolve().parent / "mandate_templates"
ROLES = ("coordinator", "implementer", "reviewer")
CLAUDE_CODE = "Claude Code"
GOOGLE_ADK = "Google ADK (band-sdk)"


def slug(text: str) -> str:
    """The mandate-file slug `harness check` derives from a seat's display name."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


@dataclass(frozen=True)
class Seat:
    role: str
    name: str
    handle: str
    harness: str
    model: str
    band_as: str | None = None
    agent_entry: str | None = None

    @property
    def mandate_file(self) -> str:
        return f"{slug(self.name)}.md"


@dataclass(frozen=True)
class Lineup:
    name: str
    description: str
    seats: dict[str, Seat]

    def seat(self, role: str) -> Seat:
        return self.seats[role]


def load_lineups(path: Path = LINEUPS_FILE) -> dict[str, Lineup]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))["lineups"]
    lineups: dict[str, Lineup] = {}
    for name, body in raw.items():
        seats = {}
        for role in ROLES:
            if role not in body:
                raise ValueError(f"lineup {name!r} has no {role} seat")
            seats[role] = Seat(role=role, **body[role])
        lineups[name] = Lineup(name=name, description=body.get("description", ""), seats=seats)
    return lineups


def load_lineup(name: str) -> Lineup:
    lineups = load_lineups()
    if name not in lineups:
        raise SystemExit(f"unknown lineup {name!r}; choose one of {', '.join(lineups)}")
    return lineups[name]


def render_mandate(lineup: Lineup, role: str) -> str:
    seat = lineup.seat(role)
    template = (TEMPLATES_DIR / f"{role}.md").read_text(encoding="utf-8")
    return template.format(
        seat=seat.name,
        harness=seat.harness,
        model=seat.model,
        coordinator=lineup.seat("coordinator").handle,
        implementer=lineup.seat("implementer").handle,
        reviewer=lineup.seat("reviewer").handle,
    )
