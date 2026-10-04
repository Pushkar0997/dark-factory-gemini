"""Centralized configuration and model management for the Gemini Dark Factory."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)

# Verified primary models and fallback hierarchy
# Note: For official hackathon submission, mandates must declare the EXACT model
# actually used by each seat. Silent fallbacks should be restricted in strict mode.
DEFAULT_PLANNER_MODEL = "gemini-3.8-flash"
DEFAULT_BUILDER_MODEL = "gemini-3.8-flash"
DEFAULT_REVIEWER_MODEL = "gemini-3.8-flash-lite"

# Verified candidate models supported by the API
MODEL_CANDIDATES: tuple[str, ...] = (
    "gemini-3.8-flash",
    "gemini-3.8-pro",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
)


@dataclass(frozen=True)
class FactorySeatConfig:
    role: str
    config_key: str
    default_model: str
    system_prompt: str


PLANNER_PROMPT = """
You are the Planner and coordinator of this autonomous software factory.
Your job is to:
- Ingest and analyze the complete stage requirements
- Break down the task into clean, ordered, verifiable steps
- Delegate self-contained implementation assignments to @Builder
- Coordinate independent verification with @Reviewer
- Advance stages only after receiving explicit verification approval
- Never write application source code directly
Always respond clearly and use the band_send_message tool.
"""

BUILDER_PROMPT = """
You are the Builder and implementer of this autonomous software factory.
Your job is to:
- Implement features based on clear instructions from @Planner
- Write clean, correct, and maintainable code in the target stage directory
- Create and maintain the Dockerfile and RUN.md for container execution
- Run local tests and verify container startup before reporting
- Commit clean Git revisions and hand exact commit hashes to @Reviewer
- Remediate reported defects promptly
- Never accept your own work or advance stages unilaterally
Always respond clearly and use the band_send_message tool.
"""

REVIEWER_PROMPT = """
You are the Reviewer of this autonomous software factory.
Your job is to:
- Independently inspect code produced by @Builder at the reported commit hash
- Execute container builds and automated test suites independently
- Compare the implementation directly against the written specification
- Actively check for edge cases, error conditions, and concurrency safety
- Ensure backwards compatibility with all previous stage test suites
- Report concrete defects with reproduction steps, or issue explicit approval
- Never edit or fix implementation code directly
Always respond clearly and use the band_send_message tool.
"""

SEAT_CONFIGS: dict[str, FactorySeatConfig] = {
    "planner": FactorySeatConfig(
        role="Planner",
        config_key="gemini_planner",
        default_model=DEFAULT_PLANNER_MODEL,
        system_prompt=PLANNER_PROMPT.strip(),
    ),
    "builder": FactorySeatConfig(
        role="Builder",
        config_key="gemini_builder",
        default_model=DEFAULT_BUILDER_MODEL,
        system_prompt=BUILDER_PROMPT.strip(),
    ),
    "reviewer": FactorySeatConfig(
        role="Reviewer",
        config_key="gemini_reviewer",
        default_model=DEFAULT_REVIEWER_MODEL,
        system_prompt=REVIEWER_PROMPT.strip(),
    ),
}
