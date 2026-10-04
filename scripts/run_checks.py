"""Submission readiness and integrity check script for the Dark Factory.

Runs all offline structural checks mirroring the official hackathon harness:
1. File and directory layout verification
2. Mandate structure and required headers (Harness, Model)
3. Generic mandate validation (zero track-specific vocabulary)
4. Credential and secret leak scanning (verifying gitignore compliance)
5. Room export validation (if room.json is present)
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REQUIRED_FILES = ("README.md", "FACTORY.md", "pyproject.toml")
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


def is_git_tracked(rel_path: str, root: pathlib.Path) -> bool:
    """Check if a relative path is tracked by git."""
    try:
        res = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel_path],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def check_repository(root: pathlib.Path, track: str = "tablekeeper") -> tuple[list[str], list[str], list[str]]:
    """Inspect repository. Returns (errors, pending_items, notices)."""
    errors: list[str] = []
    pending: list[str] = []
    notices: list[str] = []

    # 1. Required files
    for req in REQUIRED_FILES:
        if not (root / req).is_file():
            errors.append(f"Missing required file: {req}")

    # 2. Stage layout
    for stg in STAGE_NAMES:
        stg_dir = root / stg
        if not stg_dir.is_dir():
            errors.append(f"Missing stage directory: {stg}/")
        else:
            for req in ("Dockerfile", "RUN.md"):
                if not (stg_dir / req).is_file():
                    errors.append(f"Missing {stg}/{req}")

    # 3. Mandates verification
    mandates_dir = root / "mandates"
    if not mandates_dir.is_dir():
        errors.append("Missing mandates/ directory")
    else:
        mandate_files = sorted(mandates_dir.glob("*.md"))
        # Exclude README.md if present
        mandates_to_check = [f for f in mandate_files if f.name.lower() != "readme.md"]
        if len(mandates_to_check) < 3:
            errors.append(f"Found only {len(mandates_to_check)} mandate file(s); minimum 3 required")

        for mf in mandates_to_check:
            text = mf.read_text(encoding="utf-8", errors="replace")
            for field in MANDATE_FIELDS:
                if not re.search(rf"(?im)^[-*_ \t]*{field}[*_ \t]*:[*_ \t]*[^*_\s]", text):
                    errors.append(f"mandates/{mf.name} missing `{field}:` declaration")

            # Check track-specific vocabulary leakage
            # Tablekeeper terms
            tk_terms = {"booking", "party", "walk-in", "waitlist", "tablekeeper", "seat_party", "leave_table"}
            pocket_terms = {"pocketful", "ledger", "split", "charge", "refund", "balance", "transfer"}
            active_terms = tk_terms if track == "tablekeeper" else pocket_terms

            for line_no, line in enumerate(text.splitlines(), 1):
                lower_line = line.lower()
                for term in active_terms:
                    if re.search(rf"\b{re.escape(term)}\b", lower_line):
                        errors.append(
                            f"Gate 4 violation: mandates/{mf.name}:{line_no} leaks track token '{term}'. "
                            "Mandates must describe factory operation, never problem specifics."
                        )

    # 4. Room export (room.json)
    room_file = root / "room.json"
    if not room_file.is_file():
        pending.append(
            "room.json is not present (expected before live run; export full session from Band console upon completion)"
        )
    else:
        try:
            room_data = json.loads(room_file.read_text(encoding="utf-8"))
            messages = room_data.get("messages", [])
            seats = {
                m["senderId"]: m.get("senderName") or m["senderId"]
                for m in messages
                if m.get("senderId") and str(m.get("senderType", "")).lower() == "agent"
            }
            if len(seats) < 3:
                errors.append(f"room.json has only {len(seats)} agent seats (minimum 3 required)")
            else:
                notices.append(f"room.json verified: {len(seats)} seats, {len(messages)} messages")
        except Exception as exc:
            errors.append(f"room.json could not be parsed: {exc}")

    # 5. Secret scanning
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file():
            # Check if this is a sensitive local config file
            is_local_secret_file = path.name in (".env", "agent_config.yaml")
            if is_local_secret_file:
                if is_git_tracked(rel, root):
                    errors.append(f"CRITICAL SECURITY: {rel} is tracked by Git! Remove immediately with git rm --cached.")
                else:
                    notices.append(f"Local credential file '{rel}' is safely ignored by Git.")
                continue

            # For general text files, check pattern matches
            if path.suffix.lower() in TEXT_EXTS or path.name in ("Dockerfile",):
                is_config = path.suffix.lower() in CONFIG_SUFFIXES
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                    for name, pat in SECRETS:
                        if name in CONFIG_ONLY and not is_config:
                            continue
                        if pat.search(text):
                            if "example" in path.name.lower() or path.suffix == ".md":
                                continue
                            if is_git_tracked(rel, root):
                                errors.append(f"Git-tracked file {rel} matches credential pattern: {name}")
                            else:
                                notices.append(f"Untracked file {rel} matches credential pattern: {name}")
                            break
                except Exception:
                    pass

    return errors, pending, notices


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    track = sys.argv[1] if len(sys.argv) > 1 else "tablekeeper"
    print(f"============================================================")
    print(f"  Dark Factory Submission Readiness Scanner")
    print(f"  Target Root: {root}")
    print(f"  Track:       {track}")
    print(f"============================================================\n")

    errors, pending, notices = check_repository(root, track)

    if notices:
        print("[NOTICES & ENVIRONMENT STATE]")
        for n in notices:
            print(f"  - {n}")
        print()

    if pending:
        print("[PENDING POST-LIVE RUN ARTIFACTS]")
        for p in pending:
            print(f"  - {p}")
        print()

    if errors:
        print(f"[ERRORS TO FIX] ({len(errors)} issue(s) detected):")
        for err in errors:
            print(f"  x {err}")
        print()
        sys.exit(1)

    print("STATUS: All pre-run structural, mandate, and security checks PASSED.")
    print("        Ready for live room rehearsal or competition run.")
    sys.exit(0)


if __name__ == "__main__":
    main()
