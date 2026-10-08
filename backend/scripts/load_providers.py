"""Clean raw Google Places results and load them into SQLite.

Reads data/raw/places_chicagoland.json (from get_providers.py), applies the
cleaning rules below, and rebuilds data/dispatch.db from scratch.

Cleaning:
  - Drop non-service businesses: any Google type outside the generic/trade set,
    unless the place also has a trade type (many real contractors carry a
    "store" tag for their showroom) or a service word in its name (Google has
    no garage door or appliance repair type, so those shops are often tagged
    "supplier" or "store"). A place tagged only "supplier" is kept unless its
    name says supply. Clearly unrelated types are always dropped.
  - Drop providers with no phone number (a lead must be able to reach them).
  - Drop providers outside Illinois.
  - Merge the gutters category into roofing.

Low-review listings are kept; the ranker applies a minimum review count.

Usage:
    python3 scripts/load_providers.py
"""

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = """
CREATE TABLE providers (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    phone        TEXT,
    website      TEXT,
    address      TEXT,
    city         TEXT,
    state        TEXT,
    zip          TEXT,
    latitude     REAL NOT NULL,
    longitude    REAL NOT NULL,
    rating       REAL,
    review_count INTEGER
);

CREATE TABLE service_categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE provider_services (
    provider_id INTEGER NOT NULL REFERENCES providers (id),
    category_id INTEGER NOT NULL REFERENCES service_categories (id),
    PRIMARY KEY (provider_id, category_id)
);
"""

CATEGORIES = {
    "plumbing": "Pipes, drains, toilets, faucets, water heaters, sewer lines, and plumbing leaks.",
    "hvac": "Heating, air conditioning, furnaces, boilers, heat pumps, and ventilation.",
    "electrical": "Wiring, outlets, switches, circuit breakers, panels, and electrical faults.",
    "roofing": "Roof leaks, damaged shingles, storm damage, roof replacement, and gutters.",
    "basement_waterproofing": "Preventing basement water: foundation cracks, seepage, sump pumps, and drainage.",
    "water_damage_restoration": "Cleanup after water damage: flooding, water extraction, drying, and mold.",
    "appliance_repair": "Washers, dryers, refrigerators, ovens, dishwashers, and other household appliances.",
    "garage_door": "Garage door repair, springs, openers, and installation.",
    "pest_control": "Insects, rodents, termites, bed bugs, and wildlife removal.",
    "handyman": "Small repairs and odd jobs: drywall, doors, fixtures, assembly, and minor carpentry.",
}
CATEGORY_MERGES = {"gutters": "roofing"}

GENERIC_TYPES = {"point_of_interest", "establishment", "service"}
TRADE_TYPES = {"general_contractor", "roofing_contractor", "electrician", "plumber", "painter"}
UNRELATED_TYPES = {
    "car_repair", "car_dealer", "truck_dealer", "insurance_agency", "lawyer",
    "educational_institution", "university", "real_estate_agency",
}
SERVICE_NAME = re.compile(
    r"repair|service|install|restoration|exterminat|pest|wildlife|mold|cleaning|heating (&|and) (air|cooling)",
    re.IGNORECASE,
)
SUPPLY_NAME = re.compile(r"suppl|wholesal|distribut|parts|local \d|academy|adjust|claims", re.IGNORECASE)


def is_service_business(place):
    types = set(place["google_types"])
    if types & UNRELATED_TYPES:
        return False
    non_service = types - GENERIC_TYPES - TRADE_TYPES
    if not non_service or types & TRADE_TYPES:
        return True
    name = place["name"]
    if SUPPLY_NAME.search(name):
        return False
    # Google tags most garage door installers "supplier" and nothing else.
    return non_service == {"supplier"} or bool(SERVICE_NAME.search(name))


def clean(raw):
    dropped = Counter()
    kept = []
    for p in raw:
        if not is_service_business(p):
            dropped["non-service business"] += 1
        elif not p["phone"]:
            dropped["no phone"] += 1
        elif p["state"] != "IL":
            dropped["outside Illinois"] += 1
        else:
            cats = {CATEGORY_MERGES.get(c) or c for c in p["categories"]}
            kept.append({**p, "categories": sorted(cats)})
    return kept, dropped


def load(db_path, providers):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    category_ids = {}
    for name, description in CATEGORIES.items():
        cur = conn.execute(
            "INSERT INTO service_categories (name, description) VALUES (?, ?)", (name, description)
        )
        category_ids[name] = cur.lastrowid
    for p in providers:
        cur = conn.execute(
            """INSERT INTO providers (name, phone, website, address, city, state, zip,
                                      latitude, longitude, rating, review_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["name"], p["phone"], p["website"], p["address"], p["city"], p["state"], p["zip"],
             p["latitude"], p["longitude"], p["rating"], p["review_count"]),
        )
        conn.executemany(
            "INSERT INTO provider_services (provider_id, category_id) VALUES (?, ?)",
            [(cur.lastrowid, category_ids[c]) for c in p["categories"]],
        )
    conn.commit()
    return conn


def main():
    parser = argparse.ArgumentParser(description="Clean raw Places data and load into SQLite.")
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "raw" / "places_chicagoland.json")
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "dispatch.db")
    args = parser.parse_args()

    raw = json.loads(args.raw.read_text())
    providers, dropped = clean(raw)
    conn = load(args.db, providers)

    print(f"Raw providers: {len(raw)}")
    for reason, n in dropped.most_common():
        print(f"  dropped ({reason}): {n}")
    print(f"Loaded providers: {len(providers)} into {args.db}\n")

    rows = conn.execute(
        """SELECT c.name, COUNT(*), SUM(p.review_count >= 10)
           FROM service_categories c
           JOIN provider_services ps ON ps.category_id = c.id
           JOIN providers p ON p.id = ps.provider_id
           GROUP BY c.id ORDER BY COUNT(*) DESC"""
    ).fetchall()
    print(f"{'category':<26} {'providers':>9} {'10+ reviews':>11}")
    for name, total, rated in rows:
        print(f"{name:<26} {total:>9} {rated:>11}")


if __name__ == "__main__":
    main()
