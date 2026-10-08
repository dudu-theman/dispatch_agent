FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependencies first so code changes don't invalidate the layer.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY dispatch_agent ./dispatch_agent
COPY data/dispatch.db ./data/dispatch.db
RUN uv sync --locked --no-dev

# One worker: conversations live in process memory (see api.py).
CMD ["sh", "-c", "exec .venv/bin/uvicorn dispatch_agent.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
