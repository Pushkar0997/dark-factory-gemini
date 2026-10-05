"""Runtime tuning and model candidates for the Google ADK seats.

Everything here is read from the environment so it can be tuned without code changes.
See FACTORY.md §"Rate limiting" for what each knob does and how to pick values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Models tried, in order, by `--allow-fallback` at startup preflight only. A fallback
# changes the model a seat runs, so the runner refuses to start a fallback model unless
# it was explicitly allowed, and logs the mismatch with the mandate loudly. Regenerate the
# mandates (scripts/render_mandates.py) with the model you actually run before a judged run.
MODEL_CANDIDATES: tuple[str, ...] = tuple(
    m.strip()
    for m in os.getenv(
        "FACTORY_MODEL_CANDIDATES",
        "gemini-3.8-flash,gemini-3.5-flash,gemini-2.5-flash,gemini-2.5-pro",
    ).split(",")
    if m.strip()
)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else int(raw)


@dataclass(frozen=True)
class RetryPolicy:
    """Turn-level retry and pacing for transient model errors (429 / 5xx / timeouts)."""

    max_attempts: int = 6          # FACTORY_MAX_RETRIES: total attempts per turn
    initial_backoff: float = 5.0   # FACTORY_INITIAL_BACKOFF: seconds before the 2nd attempt
    backoff_factor: float = 2.0    # FACTORY_BACKOFF_FACTOR
    max_backoff: float = 90.0      # FACTORY_MAX_BACKOFF: cap for one wait
    jitter: float = 0.25           # FACTORY_JITTER: ± fraction of each wait, randomised
    turn_delay: float = 2.0        # FACTORY_TURN_DELAY: minimum gap between turns of one seat

    @classmethod
    def from_env(cls) -> "RetryPolicy":
        return cls(
            max_attempts=max(1, _env_int("FACTORY_MAX_RETRIES", cls.max_attempts)),
            initial_backoff=_env_float("FACTORY_INITIAL_BACKOFF", cls.initial_backoff),
            backoff_factor=_env_float("FACTORY_BACKOFF_FACTOR", cls.backoff_factor),
            max_backoff=_env_float("FACTORY_MAX_BACKOFF", cls.max_backoff),
            jitter=min(1.0, max(0.0, _env_float("FACTORY_JITTER", cls.jitter))),
            turn_delay=max(0.0, _env_float("FACTORY_TURN_DELAY", cls.turn_delay)),
        )

    def delay_for(self, attempt: int, rand: float, retry_after: float | None = None) -> float:
        """Wait before attempt `attempt + 1`. `rand` is uniform in [0, 1)."""
        base = min(self.max_backoff, self.initial_backoff * self.backoff_factor ** (attempt - 1))
        if retry_after is not None:
            base = min(self.max_backoff, max(base, retry_after))
        return max(0.0, base * (1 + self.jitter * (2 * rand - 1)))
