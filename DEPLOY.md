# Deploying Metro Mobile Plans (V1)

Architecture:

| piece | host | source |
|---|---|---|
| Frontend (Vite SPA) | **Vercel** | repo root |
| Backend API (FastAPI) | **Render** web service | `backend/` |
| Database | **Neon** PostgreSQL | — |
| Chatr refresh | on every backend redeploy (no cron) | `backend/` |

Production's database connection comes from `METROMOBILE_DATABASE_URL`, a Neon
connection string set by hand as an environment variable on the Render web
service — it is not provisioned by `render.yaml` (see §2).

Bell / Koodo / Freedom stay `official_manual` (imported from the reviewed
`backend/fixtures/ranking/v1_dataset.json`). Only Chatr is `official_automated`.

---

## 1. GitHub

The project must be in a GitHub repo first (Render + Vercel deploy from it).
A first commit is already staged locally.

```sh
# create an EMPTY repo on github.com (no README/licence), then:
git remote add origin git@github.com:<you>/metro-mobile-plans.git
git push -u origin main
```

The repo contains the reviewed plan dataset but no secrets or raw carrier
captures (those are git-ignored).

## 2. Render — API (Blueprint)

`render.yaml` at the repo root defines the backend web service. It also
provisions a Render-managed PostgreSQL instance, but **production does not use
it** — see the database note below.

1. render.com → **New → Blueprint** → connect the GitHub repo.
2. Render shows: 1 PostgreSQL, 1 web service (`metromobile-api`). Approve.
3. On `metromobile-api`, set:
   - `METROMOBILE_HTTP_USER_AGENT` = e.g.
     `metro-mobile-plans/1.0 (+https://<your-site>; contact: you@example.com)`
   - `METROMOBILE_FRONTEND_ORIGIN` = your Vercel URL(s), comma-separated
     (fill in after step 3 of §3).
   - `METROMOBILE_DATABASE_URL` = your Neon PostgreSQL connection string.
     Not declared in `render.yaml` — set it by hand. It takes priority over
     the Blueprint-injected `DATABASE_URL` (see `metromobile/config.py`),
     which is how production runs on Neon instead of the Render-provisioned
     Postgres instance below.
4. First deploy runs: `alembic upgrade head` → `metromobile bootstrap`
   (reproduces the 26 verified / 24 rankable V1 dataset) → `uvicorn`.
   Watch the deploy log — bootstrap prints the plan counts and fails the
   deploy if they drift.

Backend URL will be `https://metromobile-api.onrender.com` (or similar).
Health check: `GET /health`.

**Database:** production runs on **Neon** PostgreSQL, connected via the
hand-set `METROMOBILE_DATABASE_URL` above. The `databases:` block in
`render.yaml` still provisions a separate Render-managed PostgreSQL instance —
it is left in place because it's part of a working deployment, but it is not
the production database and is currently unused.

**Chatr refresh:** there is no scheduled cron. Chatr's plans refresh once on
every backend redeploy, as part of the web service's `startCommand`.

**Free-tier caveats:** the Render web service sleeps after 15 min idle (cold
start ~30–50 s). Neon's free tier and Render's free-tier Postgres each have
their own separate limits — check current terms for whichever you rely on.

## 3. Vercel — frontend

1. vercel.com → **Add New → Project** → import the GitHub repo.
2. Root Directory: **repo root** (leave default). Framework auto-detects
   **Vite** (`vercel.json` is present).
3. Environment Variable:
   - `VITE_API_BASE_URL` = the Render backend URL from §2 (no trailing slash),
     e.g. `https://metromobile-api.onrender.com`
4. Deploy. Then copy the Vercel production URL back into
   `METROMOBILE_FRONTEND_ORIGIN` on the Render web service (§2 step 3) and
   redeploy the backend so CORS allows it.

## 4. Verify (curl, no browser)

```sh
API=https://metromobile-api.onrender.com
curl -s $API/health
curl -s "$API/api/meta" | python3 -m json.tool | head
curl -s "$API/api/rank?preset=overall"          | python3 -c 'import json,sys;print([r["external_id"] for r in json.load(sys.stdin)["results"]])'
curl -s "$API/api/rank?preset=cheapest"
curl -s "$API/api/rank?preset=most_data"
curl -s "$API/api/rank?preset=offers"
curl -s "$API/api/rank?preset=students"                       # eligibility false
curl -s "$API/api/rank?preset=students&student_eligible=true"  # eligibility true
curl -s "$API/api/rank?preset=overall&max_monthly_price_cad=50&require_5g=true"
```

Expected: `/api/meta` shows 27 plans / 26 verified / 24 rankable; the five
presets match `backend/tests/test_ranking.py::TestApprovedSimulationRegression`.

## Local development is unchanged

```sh
# backend
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e '.[dev]'
python -m alembic upgrade head
python -m metromobile bootstrap            # or: metromobile refresh chatr
metromobile serve                          # http://127.0.0.1:8000

# frontend (repo root)
npm install && npm run dev                 # http://localhost:5173
```

## Ongoing manual re-verification

Bell / Koodo / Freedom captures go stale after `METROMOBILE_MANUAL_REVERIFY_HOURS`
(180 days in production). Before then, re-capture each carrier's plans page and
run `metromobile reverify --manifest … --capture … --operator …` against the
production database (Neon, via `METROMOBILE_DATABASE_URL`), or they drop out
of the rankings.
