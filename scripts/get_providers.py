"""Collect real home service providers from Google Places (Text Search, New API).

Splits a bounding box into a grid of tiles, searches each candidate category in
each tile, and dedupes by Google place id. Writes raw results to JSON and prints
per-category counts and category overlap so the final category list can be chosen.

Usage:
    python3 scripts/get_providers.py                 # Chicago + inner suburbs
    python3 scripts/get_providers.py --max-calls 50  # cap API calls (cost guard)
"""

import argparse
import itertools
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.addressComponents",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.businessStatus",
        "places.types",
        "nextPageToken",
    ]
)

# Candidate category -> search query. Final categories are picked from the results.
CANDIDATE_CATEGORIES = {
    "plumbing": "plumber",
    "hvac": "heating and air conditioning contractor",
    "electrical": "electrician",
    "roofing": "roofing contractor",
    "basement_waterproofing": "basement waterproofing",
    "water_damage_restoration": "water damage restoration",
    "appliance_repair": "appliance repair",
    "garage_door": "garage door repair",
    "pest_control": "pest control",
    "handyman": "handyman",
    "gutters": "gutter repair",
}

# Chicago city limits plus the inner-ring suburbs.
DEFAULT_BBOX = {"south": 41.64, "west": -87.95, "north": 42.07, "east": -87.52}
DEFAULT_TILE_DEG = 0.1  # ~11 km north-south, ~8 km east-west at this latitude


def load_api_key():
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    env_path = ROOT / ".env"
    if not key and env_path.exists():
        for line in env_path.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "GOOGLE_PLACES_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        sys.exit("GOOGLE_PLACES_API_KEY not set (env or .env)")
    return key


def make_tiles(bbox, step):
    rows = max(1, round((bbox["north"] - bbox["south"]) / step))
    cols = max(1, round((bbox["east"] - bbox["west"]) / step))
    dlat = (bbox["north"] - bbox["south"]) / rows
    dlng = (bbox["east"] - bbox["west"]) / cols
    return [
        {
            "low": {"latitude": bbox["south"] + r * dlat, "longitude": bbox["west"] + c * dlng},
            "high": {
                "latitude": bbox["south"] + (r + 1) * dlat,
                "longitude": bbox["west"] + (c + 1) * dlng,
            },
        }
        for r in range(rows)
        for c in range(cols)
    ]


class CallLimitReached(Exception):
    pass


class PlacesClient:
    def __init__(self, api_key, max_calls):
        self.api_key = api_key
        self.max_calls = max_calls
        self.calls = 0

    def search(self, query, rectangle, page_token=None):
        if self.calls >= self.max_calls:
            raise CallLimitReached(f"hit --max-calls limit ({self.max_calls})")
        body = {
            "textQuery": query,
            "pageSize": 20,
            "locationRestriction": {"rectangle": rectangle},
        }
        if page_token:
            body["pageToken"] = page_token
        req = urllib.request.Request(
            SEARCH_URL,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": FIELD_MASK,
            },
        )
        self.calls += 1
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Places API {e.code}: {e.read().decode()}") from e


def address_part(place, part_type):
    for comp in place.get("addressComponents", []):
        if part_type in comp.get("types", []):
            return comp.get("shortText")
    return None


def to_provider(place):
    return {
        "place_id": place["id"],
        "name": place.get("displayName", {}).get("text"),
        "phone": place.get("nationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "address": place.get("formattedAddress"),
        "city": address_part(place, "locality"),
        "state": address_part(place, "administrative_area_level_1"),
        "zip": address_part(place, "postal_code"),
        "latitude": place["location"]["latitude"],
        "longitude": place["location"]["longitude"],
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount"),
        "google_types": place.get("types", []),
        "categories": [],
    }


def collect(client, tiles, categories, providers, capped_tiles):
    """Fills providers and capped_tiles in place, so partial results survive a stop."""
    for cat, query in categories.items():
        before = sum(cat in p["categories"] for p in providers.values())
        for rect in tiles:
            token, seen = None, 0
            for _ in range(3):  # Text Search returns at most 3 pages of 20
                data = client.search(query, rect, token)
                for place in data.get("places", []):
                    seen += 1
                    if place.get("businessStatus") != "OPERATIONAL":
                        continue
                    p = providers.setdefault(place["id"], to_provider(place))
                    if cat not in p["categories"]:
                        p["categories"].append(cat)
                token = data.get("nextPageToken")
                if not token:
                    break
            if seen >= 60:
                capped_tiles[cat] += 1
        after = sum(cat in p["categories"] for p in providers.values())
        print(f"  {cat:<26} +{after - before:>4} providers  (calls so far: {client.calls})")


def summarize(providers, categories, capped_tiles):
    counts = Counter(c for p in providers.values() for c in p["categories"])
    print(f"\nUnique providers: {len(providers)}")
    print(f"\n{'category':<26} {'providers':>9} {'rated>=10':>9} {'capped tiles':>12}")
    for cat in categories:
        rated = sum(
            cat in p["categories"] and (p["review_count"] or 0) >= 10
            for p in providers.values()
        )
        print(f"{cat:<26} {counts[cat]:>9} {rated:>9} {capped_tiles[cat]:>12}")

    pairs = Counter()
    for p in providers.values():
        for a, b in itertools.combinations(sorted(p["categories"]), 2):
            pairs[(a, b)] += 1
    print("\nTop category overlaps (providers in both):")
    for (a, b), n in pairs.most_common(10):
        smaller = min(counts[a], counts[b])
        print(f"  {a} + {b}: {n} ({n / smaller:.0%} of the smaller category)")


def main():
    parser = argparse.ArgumentParser(description="Collect providers from Google Places.")
    parser.add_argument("--south", type=float, default=DEFAULT_BBOX["south"])
    parser.add_argument("--west", type=float, default=DEFAULT_BBOX["west"])
    parser.add_argument("--north", type=float, default=DEFAULT_BBOX["north"])
    parser.add_argument("--east", type=float, default=DEFAULT_BBOX["east"])
    parser.add_argument("--tile-deg", type=float, default=DEFAULT_TILE_DEG)
    parser.add_argument(
        "--categories",
        nargs="*",
        choices=list(CANDIDATE_CATEGORIES),
        help="subset of candidate categories (default: all)",
    )
    parser.add_argument("--max-calls", type=int, default=700)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "data" / "raw" / "places_chicagoland.json"
    )
    args = parser.parse_args()

    bbox = {"south": args.south, "west": args.west, "north": args.north, "east": args.east}
    tiles = make_tiles(bbox, args.tile_deg)
    categories = {c: CANDIDATE_CATEGORIES[c] for c in (args.categories or CANDIDATE_CATEGORIES)}
    print(
        f"{len(tiles)} tiles x {len(categories)} categories "
        f"(<= {len(tiles) * len(categories) * 3} calls, cap {args.max_calls})"
    )

    client = PlacesClient(load_api_key(), args.max_calls)
    start = time.time()
    providers, capped_tiles = {}, Counter()  # capped = tiles where a query hit the 60-result cap
    try:
        collect(client, tiles, categories, providers, capped_tiles)
    except (CallLimitReached, RuntimeError) as e:
        print(f"Stopped early, saving partial results: {e}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(list(providers.values()), indent=2))
    print(f"\nWrote {len(providers)} providers to {args.out} "
          f"({client.calls} API calls, {time.time() - start:.0f}s)")
    summarize(providers, categories, capped_tiles)


if __name__ == "__main__":
    main()
