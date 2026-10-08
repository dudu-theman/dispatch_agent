# Dispatch Agent — Database Schemas

_2026-10-08_

SQLite. Three tables: `providers`, `service_categories`, and the `provider_services` link between them. Lead state is held in memory for v1, not in the database. See [2026-10-08_system_design.md](2026-10-08_system_design.md).

Postgres types from the original sketch map to SQLite as: `SERIAL PRIMARY KEY` → `INTEGER PRIMARY KEY`, `DOUBLE PRECISION` / `DECIMAL(2,1)` → `REAL`.

## providers

Real businesses in the Chicagoland area, loaded by the offline ingest script. `rating` and `review_count` belong to the business as a whole (that is how Google and Yelp report them), so they live here and apply to every category the provider offers.

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

A fixed list of five categories, inserted when the database is created.

```sql
CREATE TABLE service_categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    description TEXT
);
```

| id | name | description |
|---|---|---|
| 1 | plumbing | Pipes, drains, toilets, faucets, water heaters, and plumbing leaks. |
| 2 | hvac | Heating, air conditioning, furnaces, heat pumps, and ventilation. |
| 3 | electrical | Wiring, outlets, circuit breakers, panels, and electrical faults. |
| 4 | roofing | Roof leaks, damaged shingles, storm damage, and roof replacement. |
| 5 | basement_waterproofing | Basement flooding, foundation leaks, water intrusion, sump pumps, and drainage issues. |

## provider_services

Many-to-many link: a provider can offer several categories.

```sql
CREATE TABLE provider_services (
    provider_id INTEGER NOT NULL REFERENCES providers (id),
    category_id INTEGER NOT NULL REFERENCES service_categories (id),
    PRIMARY KEY (provider_id, category_id)
);
```
