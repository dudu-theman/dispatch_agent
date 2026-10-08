# Dispatch Agent

Conversational intake for home services: a homeowner describes a problem, the agent asks questions until the lead is dispatchable, then returns ranked local providers. See `PLAN.md` and `docs/design_docs/`.

## Backend

```sh
cd backend
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

### Running the API

```sh
cd backend
export ANTHROPIC_API_KEY=...
uv run uvicorn dispatch_agent.api:app --reload
```

Interactive docs are at http://localhost:8000/docs. A conversation:

```sh
curl -X POST localhost:8000/conversations
# {"conversation_id": "<id>", "message": "Hi! What's going on at your home ..."}
curl -X POST localhost:8000/conversations/<id>/messages \
  -H 'Content-Type: application/json' -d '{"message": "My kitchen sink is clogged"}'
# {"type": "question", ...} until the lead is complete, then {"type": "lead", ...}
```

### Rebuilding the database

`backend/data/dispatch.db` is committed. To rebuild it from source data:

```sh
cd backend
uv run python scripts/get_providers.py     # Google Places; needs GOOGLE_PLACES_API_KEY in backend/.env
uv run python scripts/get_zip_centroids.py # Census ZIP centroids
uv run python scripts/load_providers.py    # rebuilds data/dispatch.db
```
