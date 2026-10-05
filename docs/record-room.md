# Guide: Exporting and Verifying `room.json`

## 1. Overview
The `room.json` file is the definitive proof of your dark-factory run. It proves that the service was built through genuine agent collaboration in a Band room rather than being authored by hand.

Judges verify:
- At least three distinct agent seats participated.
- At least two of your own seats exchanged messages using each other's literal `@handles`, with a reply in each direction.
- The Git commit hashes and implementation files match the work discussed and checked in the room.

---

## 2. Export Procedure

Follow these steps precisely after the factory completes its run:

1. **Open Room in Band Console**:
   - In Band Desktop, navigate to the room where your factory operated.
   - Click the `⋮` (more options) menu at the top-right corner.
   - Select **Open in Band**. The session opens in your browser console under **Sessions**.

2. **Download Full Session**:
   - In the web console, click the room's `⋮` menu at top-right.
   - Select **Download → Download full session**.
   - **CRITICAL**: Do **NOT** use "Download filtered". The download must contain the complete, unpruned message stream (`scope: full`).

3. **Placement and Naming**:
   - Move the downloaded JSON file to the root of your repository:
     ```bash
     mv ~/Downloads/<RoomName>.json ./room.json
     ```
   - Ensure the filename is exactly `room.json` (lowercase).

---

## 3. Secret Audit & Redaction Check

Because the downloaded room log records tool calls and raw outputs:
1. Scan `room.json` for any inadvertently captured API keys or passwords.
2. If any credential appears in `room.json`:
   - Immediately rotate the credential.
   - Replace the sensitive token in `room.json` with `[REDACTED]`.
   - Do not alter message structures, timestamps, sender IDs, or content payloads.

---

## 4. Verification Check

Before committing `room.json`, execute:

```bash
uv run python scripts/run_checks.py --repo <result repo> --track tablekeeper
```

Or using the official event harness:

```bash
cd ~/band-work/kickoff && ~/band-work/.venv/bin/python -m harness check <result repo> --track tablekeeper
```

Verify that the check reports `ok — gates 1, 2 and the mandate part of gate 4 pass`.
