"""Unit tests for the factory's own logic (no network, no Band, no model calls)."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
KICKOFF_VOCAB = None

from factory.config import RetryPolicy  # noqa: E402
from factory.lineup import ROLES, load_lineups, render_mandate, slug  # noqa: E402


class _Err(Exception):
    def __init__(self, msg: str, code: int | None = None):
        super().__init__(msg)
        if code is not None:
            self.code = code


def test_transient_classification():
    from factory.adapter import is_transient_error

    assert is_transient_error(_Err("429 RESOURCE_EXHAUSTED quota", 429))
    assert is_transient_error(_Err("503 UNAVAILABLE: model overloaded"))
    assert is_transient_error(TimeoutError("timed out"))
    assert not is_transient_error(_Err("404 NOT_FOUND model gemini-x", 404))
    assert not is_transient_error(_Err("400 INVALID_ARGUMENT", 400))
    assert not is_transient_error(ValueError("bad schema"))


def test_retry_after_parsing():
    from factory.adapter import retry_after_seconds

    assert retry_after_seconds(_Err("Please retry in 37.5s.")) == 37.5
    assert retry_after_seconds(_Err("'retryDelay': '12s'")) == 12.0
    assert retry_after_seconds(_Err("no hint")) is None


def test_backoff_is_bounded_jittered_and_honours_retry_after():
    p = RetryPolicy(initial_backoff=5, backoff_factor=2, max_backoff=60, jitter=0.25)
    assert p.delay_for(1, 0.5) == 5
    assert p.delay_for(3, 0.5) == 20
    assert p.delay_for(10, 0.5) == 60          # capped
    assert 3.75 <= p.delay_for(1, 0.0) <= 6.25 and 3.75 <= p.delay_for(1, 0.999) <= 6.25
    assert p.delay_for(1, 0.5, retry_after=30) == 30
    assert p.delay_for(1, 0.5, retry_after=500) == 60


def test_zero_env_values_are_respected(monkeypatch):
    monkeypatch.setenv("FACTORY_TURN_DELAY", "0")
    monkeypatch.setenv("FACTORY_JITTER", "0")
    p = RetryPolicy.from_env()
    assert p.turn_delay == 0 and p.jitter == 0


@pytest.mark.parametrize("lineup", list(load_lineups()))
def test_every_lineup_renders_truthful_mandates(lineup):
    lu = load_lineups()[lineup]
    for role in ROLES:
        seat = lu.seat(role)
        text = render_mandate(lu, role)
        assert re.search(rf"(?m)^Harness: {re.escape(seat.harness)}$", text)
        assert re.search(rf"(?m)^Model: {re.escape(seat.model)}$", text)
        assert "{" not in text and "}" not in text, "unfilled placeholder"
        for other in ROLES:
            assert f"@{lu.seat(other).handle}" in text
        assert seat.mandate_file == f"{slug(seat.name)}.md"


def test_workspace_paths_cannot_escape(tmp_path, monkeypatch):
    from factory import workspace_tools as wt

    (tmp_path / "inside.txt").write_text("hello\nworld\n")
    monkeypatch.setenv("FACTORY_WORKSPACE", str(tmp_path))
    assert wt.resolve_inside("inside.txt") == (tmp_path / "inside.txt").resolve()
    with pytest.raises(wt.WorkspaceError):
        wt.resolve_inside("../outside.txt")
    with pytest.raises(wt.WorkspaceError):
        wt.resolve_inside("/etc/passwd")
    (tmp_path / "link").symlink_to("/etc")
    with pytest.raises(wt.WorkspaceError):
        wt.resolve_inside("link/passwd")


def test_workspace_tools_round_trip_and_hide_secrets(tmp_path, monkeypatch):
    from factory import workspace_tools as wt

    monkeypatch.setenv("FACTORY_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "should-not-leak")
    run = asyncio.run
    run(wt.write_file(wt.WriteFileInput(path="a/b.txt", content="x\ny\n")))
    assert "2\ty" in run(wt.read_file(wt.ReadFileInput(path="a/b.txt")))
    assert run(wt.list_dir(wt.ListDirInput(path="."))) == "a/"
    out = run(wt.run_command(wt.RunCommandInput(command="echo ${GOOGLE_API_KEY:-absent}; pwd", cwd="a")))
    assert "exit: 0" in out and "absent" in out and "should-not-leak" not in out
    assert "timeout" in run(wt.run_command(wt.RunCommandInput(command="sleep 5", timeout_s=1)))
