# Replit Deployment Guide — Tablekeeper Stage 4 Demo

> 🚀 **Current Active Live Demo**: The primary live demo is deployed on Render at **[https://tablekeeper-demo-rxjp.onrender.com](https://tablekeeper-demo-rxjp.onrender.com)**.
> This guide documents the optional / alternative one-click deployment path on Replit for evaluators or developers wishing to run an isolated instance in a cloud workspace.

---

## 1. Architectural Overview & Boundaries

- **Role of Replit**: Replit provides an optional, interactive cloud IDE and self-hosting path for hackathon evaluators. The active public deployment is hosted on Render.
- **Competition Integrity**: The official judged competition artifacts (`stage-4/Dockerfile`, `stage-4/RUN.md`, `room.json`, mandates) are unchanged and remain the immutable source of truth.
- **Application Characteristics**:
  - **Directory Served**: `stage-4/`
  - **Entrypoint**: `stage-4/app.py`
  - **Static Assets**: `stage-4/static/` (`index.html`, `app.css`, `app.js`)
  - **Runtime Dependencies**: Python 3.10+ standard library + `tzdata` (for `zoneinfo` time zone resolution)
  - **State Storage**: In-memory (no external database or migrations needed)
  - **Host & Port**: Binds to `0.0.0.0` and respects `$PORT` (defaulting to `8080` if unset)

---

## 2. Configuration Files Present

| File | Purpose |
|---|---|
| [`.replit`](../.replit) | Declares Python 3.12 module, run command (`python stage-4/app.py`), port mapping (`8080` -> `80`), and deployment target. |
| [`replit.nix`](../replit.nix) | Declares Nix package dependencies (`python312Full`, `tzdata`). |
| [`requirements.txt`](../requirements.txt) | Pinned `tzdata>=2024.1` for pip installation upon repo import. |

---

## 3. Step-by-Step Deployment Instructions

### Step 1: Import into Replit
1. Open [Replit](https://replit.com) and log in.
2. Click **"+ Create Repl"** in the top left/sidebar.
3. Select **"Import from GitHub"**.
4. Enter the GitHub repository URL:
   ```text
   https://github.com/Pushkar0997/dark-factory-gemini
   ```
5. Click **"Import from GitHub"**.

### Step 2: Verify Workspace Run Configuration
Replit will automatically parse `.replit`. If prompted for the run configuration:
- **Language**: Python
- **Run command**: `python stage-4/app.py`

Click the green **"Run"** button at the top. Replit will:
1. Install dependencies from `requirements.txt` (`tzdata`).
2. Start the HTTP server: `Server(("0.0.0.0", port), Handler).serve_forever()`.
3. Detect the listening port and open the interactive Webview panel.

### Step 3: Deploy to Production (Public HTTPS URL)
To provide a persistent public link that remains online without keeping your browser tab open:
1. In the top right corner of the Replit workspace, click **"Deploy"**.
2. Select **Autoscale** (or Reserved VM / Cloudrun).
3. Confirm the deployment settings:
   - **Run Command**: `python stage-4/app.py`
   - **Port**: `8080`
   - **Environment Variables**: None required.
4. Click **"Deploy your Repl"**.
5. Once deployment completes, Replit displays your live HTTPS URL:
   ```text
   https://<repl-name>.<your-username>.replit.app
   ```

---

## 4. Deployment Verification & Route Testing

Once deployed (or running locally), test the following endpoints:

### Core Browser UI Screens
- **`GET /`**: Home screen with restaurant selection, date/party size inputs, and reservation booking form.
- **`GET /signup`**: User registration form (name, email, password).
- **`GET /login`**: User login form.
- **`GET /lookup`**: Direct lookup screen for reservation reference codes.

### API & Static Endpoints
- **`GET /health`**: Health probe returning HTTP 200:
  ```json
  {"status": "ok"}
  ```
- **`GET /restaurants`**: Catalog of active restaurants (`r_anker`, `r_two`).
- **`GET /static/app.css`**: CSS stylesheet (Content-Type: `text/css; charset=utf-8`).
- **`GET /static/app.js`**: Frontend JavaScript (Content-Type: `application/javascript; charset=utf-8`).

### Quick Smoke Test via cURL
Replace `BASE_URL` with your local host or Replit URL:

```bash
BASE_URL="http://localhost:8080"

# 1. Health check
curl -s -i "$BASE_URL/health"

# 2. Main UI screen
curl -s -i "$BASE_URL/"

# 3. Lookup screen
curl -s -i "$BASE_URL/lookup"

# 4. List restaurants
curl -s "$BASE_URL/restaurants" | jq .

# 5. Check availability
curl -s "$BASE_URL/availability?restaurant_id=r_anker&party_size=2&date=2026-10-15" | jq .
```

---

## 5. What NOT to Change

To protect the competition result and eligibility:
- ❌ **Do NOT modify any files inside `stage-1/`, `stage-2/`, `stage-3/`, or `stage-4/`**.
  - All stage folders were authored by the autonomous Implementer agent during the judged session. Changing them breaks git author hygiene and invalidates the official run.
- ❌ **Do NOT modify `room.json`**.
  - `room.json` is the cryptographic proof of the live multi-agent session.
- ❌ **Do NOT modify `mandates/`**.
  - Mandates match the judged lineup.
- ❌ **Do NOT add heavy frameworks or databases**.
  - Stage 4 was purposefully engineered using Python standard library + `tzdata`. Adding Flask, FastAPI, SQLite, or PostgreSQL is unnecessary and risks breaking container contracts.
