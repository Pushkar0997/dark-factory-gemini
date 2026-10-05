"""Factory and submission checks. Nothing here can make a stage pass; it only reports.

    python scripts/run_checks.py                         # factory self-checks (offline)
    python scripts/run_checks.py --repo <result repo> --track tablekeeper
                                                         # + official `harness check` on it
    python scripts/run_checks.py --repo <result repo> --track tablekeeper --stage 1 [--isolated]
                                                         # + official `harness run` for a stage

Factory self-checks:
  1. unit tests (tests/)                                 — retry, backoff, sandbox, rendering
  2. every lineup renders mandates with real Harness/Model lines and no placeholders
  3. this repo's mandates/ equal one lineup's rendering exactly (no hand drift), and
     contain none of the official track vocabulary (the organisers' own list)
  4. no stage-N/ folders committed in the factory repo by hand
  5. local secrets files (.env, agent_config.yaml) are git-ignored and untracked

The official harness lives in the kickoff checkout; point $KICKOFF_DIR at it (default
~/band-work/kickoff) and $HARNESS_PYTHON at a Python with harness/requirements.txt
installed (default ~/band-work/.venv/bin/python).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from factory.lineup import ROLES, load_lineups, render_mandate  # noqa: E402

KICKOFF = Path(os.getenv("KICKOFF_DIR", Path.home() / "band-work" / "kickoff")).expanduser()
HARNESS_PY = os.getenv("HARNESS_PYTHON", str(Path.home() / "band-work" / ".venv" / "bin" / "python"))

results: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"\n       {detail}" if detail else ""))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout


def check_unit_tests() -> None:
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")],
                         capture_output=True, text=True)
    tail = (res.stdout or res.stderr).strip().splitlines()[-1:] or ["no output"]
    record("unit tests", res.returncode == 0, tail[0])


def check_lineups_and_mandates() -> None:
    lineups = load_lineups()
    record("lineups render", True, ", ".join(lineups))
    mandates = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "mandates").glob("*.md")}
    match = None
    for name, lineup in lineups.items():
        expected = {lineup.seat(r).mandate_file: render_mandate(lineup, r) for r in ROLES}
        if expected == mandates:
            match = name
    record("mandates/ equals a rendered lineup", match is not None,
           f"lineup: {match}" if match else
           f"found {sorted(mandates)}; run scripts/render_mandates.py --lineup <name>")

    vocab_file = KICKOFF / "harness" / "vocabulary.py"
    if not vocab_file.is_file():
        record("mandates use no track vocabulary", False, f"{vocab_file} not found; set KICKOFF_DIR")
        return
    sys.path.insert(0, str(KICKOFF))
    from harness import vocabulary  # type: ignore

    hits = []
    for track in ("tablekeeper", "pocketful"):
        banned = set(vocabulary.for_track(track))
        for fname, text in mandates.items():
            for n, line in enumerate(text.splitlines(), 1):
                hits += [f"{fname}:{n} {term} ({track})" for _k, term in vocabulary.terms_in(line) if term in banned]
    record("mandates use no track vocabulary (both tracks)", not hits, "; ".join(hits[:10]))


def check_hygiene() -> None:
    stages = [p for p in git("ls-files").splitlines() if p.split("/")[0].startswith("stage-")]
    record("no hand-written stage folders in the factory repo", not stages,
           f"tracked: {stages[:5]}" if stages else "")
    tracked = [f for f in (".env", "agent_config.yaml") if git("ls-files", f).strip()]
    ignored = all(git("check-ignore", f).strip() for f in (".env", "agent_config.yaml"))
    record("local secrets are ignored and untracked", not tracked and ignored,
           f"tracked: {tracked}" if tracked else "")


def run_harness(*args: str) -> int:
    if not (KICKOFF / "harness").is_dir():
        record(f"harness {args[0]}", False, f"kickoff checkout not found at {KICKOFF}")
        return 1
    cmd = [HARNESS_PY, "-m", "harness", *args]
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=KICKOFF).returncode


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="a submission/result repository to check with the official harness")
    ap.add_argument("--track", choices=("toy", "tablekeeper", "pocketful"))
    ap.add_argument("--stage", help="also `harness run` this stage (1-4) or 'all'")
    ap.add_argument("--isolated", action="store_true", help="run stages in isolated (judging) mode")
    ap.add_argument("--out", help="harness --out directory (must not exist)")
    args = ap.parse_args()

    print("== factory self-checks")
    check_unit_tests()
    check_lineups_and_mandates()
    check_hygiene()

    if args.repo:
        if not args.track:
            ap.error("--repo needs --track")
        repo = str(Path(args.repo).expanduser().resolve())
        print(f"\n== official harness check: {repo}")
        record("harness check", run_harness("check", repo, "--track", args.track) == 0)
        if args.stage:
            run_args = ["run", "--track", args.track, "--repo", repo]
            run_args += ["--all"] if args.stage == "all" else ["--stage", args.stage]
            if args.isolated:
                run_args += ["--mode", "isolated"]
            if args.out:
                run_args += ["--out", args.out]
            print(f"\n== official harness run (directional only: the shipped checks are a subset)")
            record(f"harness run stage {args.stage}", run_harness(*run_args) == 0,
                   "read the 'claimed stage' line above; exit status alone is not the verdict")

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed" + (f"; failed: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
