# Dispatch Agent — System Design

_2026-10-08_

A homeowner describes a problem; the agent keeps a lead state, asks one question at a time until the lead is dispatchable, then returns ranked local providers.

## Overview

The backend optimizes two outcomes: **conversion** (conversations that end in a dispatchable lead) and **lead quality** (a provider would accept and act on it). Scope is the API and data layer only; no frontend.

- **Stack:** Python, FastAPI, SQLite, Anthropic SDK (Claude with tool use for structured output).
- **Turn loop:** the LLM updates an in-memory lead state each turn; plain code decides whether the lead is complete. If not, the agent asks one question. If so, it matches and ranks providers.
- **Dispatchable lead:** service category (confident), ZIP code, problem summary, urgency, contact name and phone.
- **Provider data:** real Chicagoland businesses, loaded offline into SQLite. Schema: [2026-10-08_database_schemas.md](2026-10-08_database_schemas.md).

## Request flow

```
POST /conversations/{id}/messages
        │
        ▼
 load lead state + history
        │
        ▼
 State updater (LLM) ── merges new facts into state, drafts next question
        │
        ▼
 Sufficiency check (code) ── missing required fields?
        │
   ┌────┴─────────────┐
  yes                 no
   │                  │
   ▼                  ▼
 return ONE        Geocode ZIP → lat/lng
 question             │
                      ▼
                   Provider matcher: category → provider_services → providers within radius
                      │
                      ▼
                   Ranker → top 3
                      │
                      ▼
                   Lead builder → return lead
```

## Components

| Component | Type | Responsibility |
|---|---|---|
| API | Code | `POST /conversations` starts a lead. `POST /conversations/{id}/messages` runs one turn and returns either `{type: "question"}` or `{type: "lead"}`. `GET /leads/{id}` returns the lead. |
| Lead store | Code | In-memory dict of conversation id → lead state + message history. Lost on restart; fine for v1. |
| State updater | LLM | One Claude tool-use call per turn. Input: current state, history, new message. Output: updated fields (problem summary, category + confidence, alternate category, urgency, ZIP/address, contact, details) and a draft next question. |
| Sufficiency check | Code | Fixed list of required fields; returns them missing in priority order. Low category confidence counts as missing. Deterministic and unit-testable. |
| Question selection | Code + LLM | Uses the LLM's draft question if it targets the top missing field. Order: clarify category → ZIP → urgency → details → contact last (asking for a phone early hurts conversion). |
| Safety flag | LLM | Hazards (gas smell, sparking, active flooding near panels) set `safety_alert`; the response leads with safety guidance before any question. |
| Geocoder | Code | ZIP → lat/lng from an offline ZIP centroid table (Census ZCTA gazetteer); no API dependency at request time. |
| Provider matcher | Code | Category → `provider_services` → `providers`; bounding-box prefilter in SQL, then haversine distance within a radius (default 25 mi). |
| Ranker | Code | Score from rating and review count only (Bayesian-adjusted, so 4.9 from 8 reviews doesn't beat 4.7 from 400). Distance is a filter, not a score. Returns top 3. |
| Lead builder | Code | Assembles the dispatchable lead: customer contact, issue summary, category, urgency, location, matched providers. |
| Provider ingest | Script (offline) | Google Places Text Search per category for the local area; upserts `providers` and `provider_services`. |
