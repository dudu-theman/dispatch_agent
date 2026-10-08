import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dispatch.db"

# Provider search
RADIUS_MILES = 25
MIN_REVIEWS = 10
TOP_N = 3
# Bayesian prior: how many "average" reviews each provider's rating is blended with.
# Median review count among eligible providers is ~40, so 50 keeps a 4.9 from 15
# reviews below a 4.7 from 400.
PRIOR_WEIGHT = 50

# Lead completeness
# Lowest category confidence ("low", "medium", "high") that counts as known. Below it,
# the agent asks a clarifying question (e.g. "water in the basement": plumbing or
# waterproofing?).
MIN_CATEGORY_CONFIDENCE = "high"

# LLM state updater
LLM_MODEL = "claude-sonnet-5-5"
# Each turn is a small extraction and latency matters in a chat, so keep effort low.
LLM_EFFORT = "low"
LLM_MAX_TOKENS = 16000

# API
# Longest homeowner message accepted, to bound the cost of one LLM turn.
MAX_MESSAGE_CHARS = 2000
# Browser origins allowed to call the API (the static UI in ui/). Comma-separated in the
# environment, e.g. UI_ORIGINS=https://dispatch-agent.vercel.app in production.
UI_ORIGINS = os.environ.get("UI_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
