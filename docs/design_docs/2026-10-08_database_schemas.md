# Dispatch Agent — Database Schemas

_2026-10-08_

SQLite. Three tables: `providers`, `service_categories`, and the `provider_services` link between them. Lead state is held in memory for v1, not in the database. See [2026-10-08_system_design.md](2026-10-08_system_design.md).

Postgres types from the original sketch map to SQLite as: `SERIAL PRIMARY KEY` → `INTEGER PRIMARY KEY`, `DOUBLE PRECISION` / `DECIMAL(2,1)` → `REAL`.

## providers

Real businesses in Chicago and the inner suburbs: collected by `scripts/get_providers.py`, cleaned and loaded by `scripts/load_providers.py` (non-service businesses and providers without a phone are dropped). `rating` and `review_count` belong to the business as a whole (that is how Google and Yelp report them), so they live here and apply to every category the provider offers.

```sql
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
    rating       REAL,     -- 0.0–5.0
    review_count INTEGER
);
```

## service_categories

Ten categories, inserted by `scripts/load_providers.py`. Chosen from a Chicagoland collection of 11 candidates; gutters was merged into roofing (51% of gutter companies are roofers).

```sql
CREATE TABLE service_categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);
```

| id | name | description |
|---|---|---|
| 1 | plumbing | Pipes, drains, toilets, faucets, water heaters, sewer lines, and plumbing leaks. |
| 2 | hvac | Heating, air conditioning, furnaces, boilers, heat pumps, and ventilation. |
| 3 | electrical | Wiring, outlets, switches, circuit breakers, panels, and electrical faults. |
| 4 | roofing | Roof leaks, damaged shingles, storm damage, roof replacement, and gutters. |
| 5 | basement_waterproofing | Preventing basement water: foundation cracks, seepage, sump pumps, and drainage. |
| 6 | water_damage_restoration | Cleanup after water damage: flooding, water extraction, drying, and mold. |
| 7 | appliance_repair | Washers, dryers, refrigerators, ovens, dishwashers, and other household appliances. |
| 8 | garage_door | Garage door repair, springs, openers, and installation. |
| 9 | pest_control | Insects, rodents, termites, bed bugs, and wildlife removal. |
| 10 | handyman | Small repairs and odd jobs: drywall, doors, fixtures, assembly, and minor carpentry. |

## provider_services

Many-to-many link: a provider can offer several categories.

```sql
CREATE TABLE provider_services (
    provider_id INTEGER NOT NULL REFERENCES providers (id),
    category_id INTEGER NOT NULL REFERENCES service_categories (id),
    PRIMARY KEY (provider_id, category_id)
);
```
