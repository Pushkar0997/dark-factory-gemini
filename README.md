# 🏭 Dark Factory — Gemini Agent

> A Gemini-powered coding agent for [BAND Desktop](https://band.ai), built for the **[WeAreDevelopers x BAND: Dark Factory Hackathon](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)**.

## What is this?

This is a software-factory agent that lives inside BAND Desktop. When you message it, it uses Google's Gemini models (via the [Google ADK](https://github.com/google/adk-python)) to plan work, write code, and check its own results — all through the BAND collaboration platform.

Built with:
- **[BAND SDK](https://pypi.org/project/band-sdk/)** — agent framework for BAND Desktop
- **[Google ADK](https://github.com/google/adk-python)** — Agent Development Kit for Gemini models
- **Gemini 3.8 Flash** — fast, capable reasoning (with automatic fallback to other models)

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A [BAND](https://band.ai) account with an agent configured
- A [Google AI API key](https://aistudio.google.com/apikey)

### Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/<your-username>/dark-factory-gemini.git
   cd dark-factory-gemini
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Configure secrets**

   Create a `.env` file (already in `.gitignore`):
   ```env
   BAND_REST_URL=https://app.band.ai
   BAND_WS_URL=wss://app.band.ai/api/v1/socket/websocket
   GOOGLE_API_KEY=your-google-api-key-here
   ```

   Create an `agent_config.yaml` (also in `.gitignore`):
   ```yaml
   gemini_builder:
     agent_id: "your-agent-uuid"
     api_key: "your-band-api-key"
   ```

4. **Run the agent**
   ```bash
   uv run python agent.py
   ```

### Model Selection

The default model is `gemini-3.8-flash`. You can choose a different one:

```bash
uv run python agent.py --model gemini-3.8-pro
uv run python agent.py -m gemini-2.5-pro
```

If the chosen model is unavailable, the agent automatically falls back through:
`gemini-3.8-flash` → `gemini-3.8-pro` → `gemini-2.5-pro` → `gemini-2.5-flash`

## 📁 Project Structure

```
dark-factory-gemini/
├── agent.py              # Main entry point — agent startup & model fallback
├── agent_config.yaml     # BAND agent credentials (git-ignored)
├── .env                  # API keys & env vars (git-ignored)
├── pyproject.toml        # Project metadata & dependencies
└── src/                  # Additional source modules
```

## 🏆 Hackathon

This project is part of the **WeAreDevelopers x BAND: Dark Factory (Hackathon Edition)** — a week-long virtual hackathon where participants build software factories in BAND Desktop: bands of coding agents that plan, implement, and self-check their work.

- 🌐 [Hackathon Page](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)
- 📅 Sept 26 – Oct 5, 2026

## 📄 License

MIT
