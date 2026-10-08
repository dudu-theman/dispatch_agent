# Dispatch Agent

Conversational intake for home services. A homeowner describes a problem in plain language ("my kitchen sink is clogged"). The agent asks one question at a time until it has a dispatchable lead, then returns the top 3 local providers for the job.

## How it works

- **Each turn**, Claude updates a structured lead state from the conversation and drafts the next question.
- **Plain code checks whether the lead is complete.** A dispatchable lead needs a confident service category, ZIP code, problem summary, urgency, and contact name and phone. Until then, the agent asks about the most important missing field. It asks for contact details last.
- **Safety hazards** (gas smell, sparking, flooding near electrical) trigger safety guidance before any other question.
- **Once the lead is complete**, the ZIP is geocoded offline. Providers in that category within 25 miles are ranked by Bayesian-adjusted rating and review count, and the top 3 are returned with the lead.

Stack: Python, FastAPI, SQLite, Anthropic SDK; a static HTML/JS chat UI in `ui/`. Design details are in `docs/design_docs/`.

## Coverage: where you can test it

Provider data covers **Chicago and its inner-ring suburbs**: about 3,000 real businesses from Google Places. Any US ZIP is recognized, but only ZIPs within about 25 miles of Chicago return providers.

| Area | ZIPs to try |
|---|---|
| Chicago | 60601 (Loop), 60614 (Lincoln Park), 60618, 60630, 60634, 60641, 60647, 60608 |
| North suburbs | 60016 (Des Plaines), 60076 / 60077 (Skokie), 60201 (Evanston), 60068 (Park Ridge), 60714 (Niles) |
| West suburbs | 60302 (Oak Park), 60126 (Elmhurst), 60527 (Burr Ridge), 60402 (Berwyn) |
| South suburbs | 60453 (Oak Lawn), 60803 (Alsip), 60455 (Bridgeview) |

Edge cases:

- **A real ZIP outside the area** (for example 10001 or 94103): the ZIP is accepted, but no providers are returned.
- **A ZIP that doesn't exist** (for example 00000): the agent asks for the ZIP again.
- **ZIPs near the edge of the radius** (for example 60085 Waukegan or 60540 Naperville): expect fewer matches.

Service categories: plumbing, hvac, electrical, roofing, appliance_repair, handyman, water_damage_restoration, pest_control, basement_waterproofing, garage_door.

## Running it

- [Local development](docs/runbooks/development.md): run the API and chat UI locally, run the tests and lint, and rebuild the provider database.
- [Deployment](docs/runbooks/deployment.md): the API on Railway and the UI on Vercel.
