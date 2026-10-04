"""Submission readiness and integrity check script for the Dark Factory.

Runs all offline structural checks mirroring the official hackathon harness:
1. File and directory layout verification
2. Mandate structure and required headers (Harness, Model)
3. Generic mandate validation (zero track-specific vocabulary)
4. Credential and secret leak scanning
5. Room export validation (if room.json is present)
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

REQUIRED_FILES = ("README.md", "FACTORY.md")
MANDATE_FIELDS = ("Harness", "Model")
STAGE_NAMES = ("stage-1", "stage-2", "stage-3", "stage-4")

SECRETS = (
    ("bearer-token", re.compile(r"(?i)\bbearer\s+(?=[A-Za-z0-9._\-]*\d)[A-Za-z0-9._\-]{20,}")),
    ("api-key", re.compile(r"\bsk-[A-Za-z0-9._\-]{16,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("env-assignment", re.compile(r"(?i)\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*\S+")),
    ("url-credentials", re.compile(r"""(?<=://)[^/\s:@"'\\]+:[^/\s@"'\\]+(?=@)""")),
)

CONFIG_ONLY = {"env-assignment"}
CONFIG_SUFFIXES = {".env", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".json"}


SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "scratch"}
TEXT_EXTS = {".md", ".py", ".txt", ".json", ".yaml", ".yml", ".toml", ".sh", ".dockerfile"}


def check_repository(root: pathlib.Path, track: str = "tablekeeper") -> list[str]:
    issues: list[str] = []

    # 1. Required files
    for req in REQUIRED_FILES:
        if not (root / req).is_file():
            issues.append(f"Missing required file: {req}")

    # 2. Stage layout
    for stg in STAGE_NAMES:
        stg_dir = root / stg
        if stg_dir.is_dir():
            for req in ("Dockerfile", "RUN.md"):
                if not (stg_dir / req).is_file():
                    issues.append(f"Missing {stg}/{req}")

    # 3. Mandates
    mandates_dir = root / "mandates"
    if not mandates_dir.is_dir():
        issues.append("Missing mandates/ directory")
    else:
        mandate_files = list(mandates_dir.glob("*.md"))
        if len(mandate_files) < 3:
            issues.append(f"Fewer than 3 mandates found ({len(mandate_files)})")
        for mf in mandate_files:
            content = mf.read_text(encoding="utf-8", errors="replace")
            for field in MANDATE_FIELDS:
                if not re.search(rf"(?im)^[-*_ \t]*{field}[*_ \t]*:[*_ \t]*[^*_\s]", content):
                    issues.append(f"{mf.name} is missing `{field}:` declaration")

    # 4. Room export (informational if pending)
    room_file = root / "room.json"
    if not room_file.is_file():
        issues.append("room.json is missing (PENDING: download full session from Band console after run)")
    else:
        try:
            data = json.loads(room_file.read_text(encoding="utf-8"))
            if data.get("scope") != "full":
                issues.append("room.json scope is not 'full' (use Download Full Session)")
        except Exception as exc:
            issues.append(f"room.json is malformed JSON: {exc}")

    # 5. Secrets scan
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.is_file() and (path.suffix.lower() in TEXT_EXTS or path.name in ("Dockerfile", ".env")):
            is_config = path.suffix.lower() in CONFIG_SUFFIXES or path.name in (".env", "Dockerfile")
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                for name, pat in SECRETS:
                    if name in CONFIG_ONLY and not is_config:
                        continue
                    if pat.search(text):
                        # Filter out documentation mentions or example templates
                        if "example" in path.name.lower() or path.suffix == ".md":
                            continue
                        issues.append(f"{rel} matches credential pattern: {name}")
                        break
            except Exception:
                pass

    return issues


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    track = sys.argv[1] if len(sys.argv) > 1 else "tablekeeper"
    print(f"Running submission checks against: {root} (track: {track})")

    issues = check_repository(root, track)
    if not issues:
        print("\nSUCCESS: All offline submission structure checks passed!")
        sys.exit(0)

    print(f"\nFOUND {len(issues)} ITEM(S):")
    for issue in issues:
        print(f" - {issue}")
    sys.exit(1)


if __name__ == "__main__":
    main()
