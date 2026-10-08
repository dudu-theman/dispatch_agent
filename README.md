# Dispatch Agent

Conversational intake for home services: a homeowner describes a problem, the agent asks questions until the lead is dispatchable, then returns ranked local providers. See `PLAN.md` and `docs/design_docs/`.

## Backend

```sh
cd backend
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

### Rebuilding the database

`backend/data/dispatch.db` is committed. To rebuild it from source data:

```sh
cd backend
uv run python scripts/get_providers.py     # Google Places; needs GOOGLE_PLACES_API_KEY in backend/.env
uv run python scripts/get_zip_centroids.py # Census ZIP centroids
uv run python scripts/load_providers.py    # rebuilds data/dispatch.db
```
