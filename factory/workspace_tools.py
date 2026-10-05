"""Sandboxed workspace tools that let a Google ADK seat read, write and run commands.

The Band SDK's Google ADK adapter only bridges Band platform tools (messaging, room
participants, memory). A seat that must write code, commit or run checks needs more, so
these tools are passed to the adapter as `additional_tools`.

Every path is resolved and must stay inside the workspace root (``FACTORY_WORKSPACE``);
symlinks that escape it are refused. Commands run with that root as the boundary for their
working directory, a timeout, a truncated output, and an environment with model and Band
credentials removed, so a command cannot echo a key into the room.

These are guard rails against mistakes, not a security boundary: a command can still reach
anything the OS user can. Run seats with workspace tools on a machine (or Docker Sandbox)
you are willing to let them change.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

from band.runtime.custom_tools import CustomToolDef, declares_turn_effect
from band.runtime.tools.types import TurnEffect

MAX_OUTPUT_CHARS = 20_000
MAX_READ_LINES = 2_000
DEFAULT_TIMEOUT_S = 600
MAX_TIMEOUT_S = 1_800
# Credentials a command must never see (and therefore can never print into the room).
_SECRET_ENV = re.compile(r"(?i)(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)")


class WorkspaceError(ValueError):
    """Raised for a path or command the sandbox refuses; the text goes back to the model."""


def workspace_root() -> Path:
    raw = os.getenv("FACTORY_WORKSPACE", "").strip()
    if not raw:
        raise WorkspaceError("FACTORY_WORKSPACE is not set; workspace tools are disabled")
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise WorkspaceError(f"FACTORY_WORKSPACE {root} is not a directory")
    return root


def resolve_inside(path: str, root: Path | None = None) -> Path:
    """Resolve `path` (absolute, or relative to the root) and refuse anything outside root."""
    root = root or workspace_root()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise WorkspaceError(f"{path} is outside the workspace {root}")
    return resolved


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    head = MAX_OUTPUT_CHARS // 4
    tail = MAX_OUTPUT_CHARS - head
    return f"{text[:head]}\n… [{len(text) - MAX_OUTPUT_CHARS} chars truncated] …\n{text[-tail:]}"


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}


class ReadFileInput(BaseModel):
    """Read a UTF-8 text file inside the workspace. Returns numbered lines."""

    path: str = Field(description="Absolute path, or path relative to the workspace root")
    offset: int = Field(default=0, ge=0, description="First line to return (0-based)")
    limit: int = Field(default=MAX_READ_LINES, ge=1, le=MAX_READ_LINES)


class ListDirInput(BaseModel):
    """List a directory inside the workspace (one level; directories end with '/')."""

    path: str = Field(default=".", description="Absolute path, or relative to the workspace root")


class WriteFileInput(BaseModel):
    """Create or overwrite a UTF-8 text file inside the workspace (parents are created)."""

    path: str = Field(description="Absolute path, or relative to the workspace root")
    content: str = Field(description="The complete new file content")


class RunCommandInput(BaseModel):
    """Run a shell command (bash) inside the workspace and return exit code and output.

    Use it for git, docker, test runners and the official harness. Non-interactive only.
    """

    command: str = Field(description="The bash command line to run")
    cwd: str = Field(default=".", description="Working directory inside the workspace")
    timeout_s: int = Field(default=DEFAULT_TIMEOUT_S, ge=1, le=MAX_TIMEOUT_S)


@declares_turn_effect(TurnEffect.OBSERVE)
async def read_file(args: ReadFileInput) -> str:
    target = resolve_inside(args.path)
    if not target.is_file():
        raise WorkspaceError(f"{args.path} is not a file")
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    chunk = lines[args.offset : args.offset + args.limit]
    body = "\n".join(f"{args.offset + i + 1:6}\t{line}" for i, line in enumerate(chunk))
    more = len(lines) - (args.offset + len(chunk))
    suffix = f"\n… {more} more line(s); call again with offset={args.offset + len(chunk)}" if more > 0 else ""
    return _truncate(body + suffix)


@declares_turn_effect(TurnEffect.OBSERVE)
async def list_dir(args: ListDirInput) -> str:
    target = resolve_inside(args.path)
    if not target.is_dir():
        raise WorkspaceError(f"{args.path} is not a directory")
    entries = sorted(target.iterdir(), key=lambda p: p.name)
    return "\n".join(f"{p.name}/" if p.is_dir() else p.name for p in entries) or "(empty)"


@declares_turn_effect(TurnEffect.ACT)
async def write_file(args: WriteFileInput) -> str:
    target = resolve_inside(args.path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(args.content, encoding="utf-8")
    return f"wrote {len(args.content)} chars to {target}"


@declares_turn_effect(TurnEffect.ACT)
async def run_command(args: RunCommandInput) -> str:
    cwd = resolve_inside(args.cwd)
    if not cwd.is_dir():
        raise WorkspaceError(f"{args.cwd} is not a directory")
    proc = await asyncio.create_subprocess_exec(
        "/bin/bash", "-c", args.command,
        cwd=str(cwd),
        env=_clean_env(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=args.timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return f"exit: timeout after {args.timeout_s}s (process killed)"
    return _truncate(f"exit: {proc.returncode}\n{out.decode('utf-8', errors='replace')}")


READ_ONLY_TOOLS: list[CustomToolDef] = [(ReadFileInput, read_file), (ListDirInput, list_dir)]
FULL_TOOLS: list[CustomToolDef] = READ_ONLY_TOOLS + [
    (WriteFileInput, write_file),
    (RunCommandInput, run_command),
]

# Which tools each factory role gets. The coordinator reads specifications it must paste
# into handoffs but never edits code; implementer and reviewer need the full set (the
# reviewer runs builds and checks, and its mandate forbids it from editing product code).
TOOLS_BY_ROLE: dict[str, list[CustomToolDef]] = {
    "coordinator": READ_ONLY_TOOLS,
    "implementer": FULL_TOOLS,
    "reviewer": FULL_TOOLS,
}
