# Runbook: Local development

Run the API and the chat UI on your machine.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.14 for you from `backend/.python-version`)
- `python3` (any version; only used to serve the static UI)
- An Anthropic API key

## 1. Backend (port 8000)

```sh
cd backend
uv sync
cp .env.example .env    # once, then fill in ANTHROPIC_API_KEY; .env is gitignored
set -a && source .env && set +a
uv run uvicorn dispatch_agent.api:app --reload
```

Check it: `curl localhost:8000/health` returns `{"status":"ok"}`. Interactive API docs are at http://localhost:8000/docs.

The provider database (`backend/data/dispatch.db`) is committed, so there's nothing to load. To rebuild it, see "Rebuilding the database" in the README.

## 2. Frontend (port 5173)

In a second terminal, from the repo root:

```sh
python3 -m http.server 5173 -d ui
```

Open http://localhost:5173 and start a chat.

The UI reads the API address from `ui/config.js` (`http://localhost:8000`). The API only accepts browser calls from the origins in `UI_ORIGINS` (default `http://localhost:5173,http://127.0.0.1:5173`), so serve the UI on port 5173 or set `UI_ORIGINS` when starting the backend.

## 3. Tests and lint

```sh
cd backend
uv run pytest                                   # fast suite, fake LLM
uv run pytest -m llm                            # live Claude calls; costs money
uv run ruff check . && uv run ruff format --check .
```

CI (`.github/workflows/backend.yml`) runs the fast suite and lint on every PR.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| UI shows "Couldn't reach the API" | Backend not running, or a CORS rejection: check the browser console. Serve the UI from an origin in `UI_ORIGINS`. |
| `anthropic.AuthenticationError` / 500 on first message | `ANTHROPIC_API_KEY` isn't set in the backend's shell. |
| `404 conversation not found` after editing code | `--reload` restarted the server and in-memory conversations were lost. Click "New chat". |
| Port already in use | `lsof -i :8000` (or `:5173`) and stop the old process. |
