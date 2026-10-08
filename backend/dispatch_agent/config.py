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
