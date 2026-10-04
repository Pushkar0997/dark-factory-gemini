# 🏭 Dark Factory — Gemini Multi-Agent Software Factory

> A multi-agent software factory powered by Google Gemini and [BAND Desktop](https://band.ai), built for the **[WeAreDevelopers x BAND: Dark Factory Hackathon](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)**.

## What is this?

This is a complete software factory trio that operates in BAND Desktop rooms:
- 📋 **GeminiPlanner (`planner.py`)**: Breaks down requests into structured, executable steps, assigns tasks, and coordinates workflow without writing code directly.
- 🔨 **GeminiBuilder (`builder.py`)**: Implements clean, maintainable code step-by-step according to the Planner's specifications.
- 🔍 **GeminiReviewer (`reviewer.py`)**: Reviews generated code, flags bugs, performance issues, and edge cases, and approves or requests revisions.

Built with:
- **[BAND SDK](https://pypi.org/project/band-sdk/)** — Agent framework & multi-agent room orchestration
- **[Google ADK](https://github.com/google/adk-python)** — Agent Development Kit for Gemini models
- **Gemini Models** — Dynamic model selection with automatic fallback on 404 / 503 / UNAVAILABLE errors

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- A [BAND](https://band.ai) account with 3 agents configured (`gemini_planner`, `gemini_builder`, `gemini_reviewer`)
- A [Google AI API key](https://aistudio.google.com/apikey)

### Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/Pushkar0997/dark-factory-gemini.git
   cd dark-factory-gemini
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Configure secrets**

   Create a `.env` file (git-ignored):
   ```env
   BAND_REST_URL=https://app.band.ai
   BAND_WS_URL=wss://app.band.ai/api/v1/socket/websocket
   GOOGLE_API_KEY=your-google-api-key-here
   ```

   Create an `agent_config.yaml` (git-ignored):
   ```yaml
   gemini_planner:
     agent_id: "your-planner-agent-uuid"
     api_key: "your-planner-band-api-key"

   gemini_builder:
     agent_id: "your-builder-agent-uuid"
     api_key: "your-builder-band-api-key"

   gemini_reviewer:
     agent_id: "your-reviewer-agent-uuid"
     api_key: "your-reviewer-band-api-key"
   ```

4. **Run the factory agents** (in separate terminal tabs or processes)

   ```bash
   # Terminal 1: Planner
   uv run python planner.py

   # Terminal 2: Builder
   uv run python builder.py

   # Terminal 3: Reviewer
   uv run python reviewer.py
   ```

### Model Selection & Fallback

Each agent supports custom model flags and built-in fallback lists:

```bash
uv run python planner.py --model gemini-3.6-flash
uv run python builder.py --model gemini-3.5-flash
uv run python reviewer.py --model gemini-3.5-flash-lite
```

If a chosen model is unavailable or rate-limited, the agent logs a warning and automatically attempts the next fallback in its hierarchy.

## 📁 Project Structure

```
dark-factory-gemini/
├── planner.py            # GeminiPlanner agent (planning & coordination)
├── builder.py            # GeminiBuilder agent (code implementation)
├── reviewer.py           # GeminiReviewer agent (code review & QA)
├── agent_config.yaml     # BAND credentials for all 3 agents (git-ignored)
├── .env                  # API keys & endpoints (git-ignored)
├── pyproject.toml        # Project metadata & dependencies
└── src/                  # Package sources
```

## 🏆 Hackathon

This project is part of the **WeAreDevelopers x BAND: Dark Factory (Hackathon Edition)** — a week-long virtual hackathon where participants build software factories in BAND Desktop: bands of coding agents that plan, implement, and self-check their work.

- 🌐 [Hackathon Page](https://lablab.ai/ai-hackathons/wearedevelopers-hackathon)
- 📅 Sept 26 – Oct 5, 2026

## 📄 License

MIT
