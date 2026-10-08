# Runbook: Deployment

The API runs on **Railway** (Docker, from `backend/`) and the static UI runs on **Vercel** (from `ui/`).

```
browser ──> Vercel (ui/, static) ──fetch──> Railway (backend/, FastAPI) ──> Claude API
```

## Config as code

| File | What it does |
| --- | --- |
| `backend/Dockerfile` | Builds the API image with uv; bakes in `data/dispatch.db`; listens on `$PORT`. |
| `backend/railway.toml` | Railway build/deploy config: Dockerfile builder, `/health` healthcheck, restart policy, 1 replica, redeploy only on `backend/**` changes. |
| `ui/vercel.json` | Vercel build: writes `config.js` from the `API_URL` env var, serves `ui/` as is. |

### Environment variables

| Where | Variable | Value |
| --- | --- | --- |
| Railway | `ANTHROPIC_API_KEY` | Your production key |
| Railway | `PORT` | `8000` (must match the domain's target port) |
| Railway | `UI_ORIGINS` | Your Vercel URL(s), comma-separated, no trailing slash, e.g. `https://dispatch-agent.vercel.app` |
| Vercel | `API_URL` | Your Railway public URL, no trailing slash, e.g. `https://dispatch-agent-production.up.railway.app` |

`backend/.env.example` lists the backend variables. Setting `PORT` explicitly keeps it in sync with the target port you pick when generating the domain; otherwise Railway injects its own value.

## Constraints to know

- **Run one replica, one worker.** Conversations are held in process memory, so a second replica would 404 on conversations started on the first, and every redeploy or restart drops in-flight chats. `railway.toml` pins `numReplicas = 1`.
- **The database ships in the image.** `dispatch.db` is read-only at runtime. To update provider data, rebuild the DB locally, commit it, and redeploy.
- **Vercel preview URLs aren't allowed by CORS** unless you add them to `UI_ORIGINS`. Only the production domain works by default.

## First-time setup

Do the backend first: the frontend needs its URL.

### 1. Railway (backend)

1. Railway dashboard → **New Project → Deploy from GitHub repo** → pick this repo.
2. Open the service → **Settings**:
   - **Source → Root Directory:** `/backend`
   - **Config-as-code → Railway Config File:** `/backend/railway.toml` (Railway does not look for it under the root directory, so this absolute path is required)
   - **Source → Branch:** `main`
3. **Variables:** add `ANTHROPIC_API_KEY` and `PORT=8000`. Leave `UI_ORIGINS` for step 3.
4. **Settings → Networking → Generate Domain.** Target port: **8000**. Copy the URL.
5. Deploy and check it:
   ```sh
   curl https://<railway-domain>/health          # {"status":"ok"}
   curl -X POST https://<railway-domain>/conversations
   ```

CLI alternative to steps 1–3 (after `brew install railway && railway login`):

```sh
cd backend
railway init                      # create the project
railway up                        # deploy from local files
railway variables --set ANTHROPIC_API_KEY=sk-ant-... --set PORT=8000
railway domain --port 8000        # generate the public URL
```

(Set the config file path in the dashboard either way, or connect GitHub later for push-to-deploy.)

### 2. Vercel (frontend)

1. Vercel dashboard → **Add New → Project** → import this repo.
2. **Root Directory:** `ui`. Framework preset: **Other**. Leave build/output settings alone: `ui/vercel.json` sets them.
3. **Environment Variables:** `API_URL` = the Railway URL from step 1.4 (Production, plus Preview if you want previews to work).
4. Deploy. Copy the production URL.

CLI alternative: `npm i -g vercel`, then `cd ui && vercel link && vercel env add API_URL production && vercel --prod`.

### 3. Connect them

1. Railway → Variables → set `UI_ORIGINS` to the Vercel production URL. Railway redeploys automatically.
2. Open the Vercel URL and run a chat end to end.

## Routine deploys

- **Backend:** merge to `main`. Railway rebuilds when files under `backend/` change. Let CI pass first: Railway doesn't wait for GitHub Actions unless you turn on **Settings → Wait for CI**. It's worth turning on.
- **Frontend:** merge to `main`. Vercel deploys production; PRs get preview URLs (see the CORS note above).
- **Changing `API_URL`:** redeploy on Vercel. It's baked into `config.js` at build time.
- **Custom domain:** add it in Vercel, then add it to `UI_ORIGINS` on Railway.

## Rollback

- **Railway:** Deployments tab → pick the last good deployment → **Redeploy**.
- **Vercel:** Deployments tab → last good deployment → **Promote to Production** (or `vercel rollback`).

Backend and frontend roll back independently. The API contract is small, so mismatched versions generally still work.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Railway healthcheck fails | Check deploy logs. Usually the app isn't binding `$PORT` (the Dockerfile handles this) or the build failed on `uv sync --locked` because `uv.lock` is stale: run `uv lock` and commit. |
| Railway ignores `railway.toml` / build log shows Railpack "No start command detected" | Railway didn't find `railway.toml`, so it fell back to auto-detection. Check that the config file path is `/backend/railway.toml` and that `railway.toml` and `Dockerfile` are pushed to the branch Railway deploys. |
| Domain returns "Application failed to respond" | The domain's target port doesn't match `PORT`. Set both to 8000. |
| UI: "Couldn't reach the API" + CORS error in console | `UI_ORIGINS` doesn't exactly match the page origin (scheme, no trailing slash, no path). |
| Vercel build fails at `test -n "$API_URL"` | `API_URL` isn't set for that environment (Production or Preview). The build fails on purpose so it never ships the dev `config.js`. Set it and redeploy. |
| `404 conversation not found` mid-chat | The API restarted (deploy or crash) and dropped in-memory conversations. Expected in v1. |
| 500 on every message | `ANTHROPIC_API_KEY` is missing or invalid on Railway. Check the deploy logs. |
