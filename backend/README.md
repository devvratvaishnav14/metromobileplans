# metro-mobile-plans — backend

Data pipeline + API behind the analysis screen:

```
official source → fetch → raw document (provenance) → parse → normalize
             → validate → store (SQLite / PostgreSQL) → /api/plans, /api/rank → frontend
```

FastAPI · SQLAlchemy 2 · Pydantic · Alembic · httpx · BeautifulSoup4 · Typer.
PostgreSQL is the intended target; SQLite is the zero-config local default.

## Status

**V1: four providers, all rankable.** Chatr Mobile is `official_automated`
(fetched from page-embedded JSON on <https://www.chatrwireless.com/plans> —
plain HTTPS GET, no login, no anti-bot). Bell, Koodo, and Freedom Mobile are
`official_manual` — an operator captured each carrier's official page and the
plans were imported with that capture kept as evidence.

A deterministic ranking engine (`ranking.py`) scores every rankable plan across
6 components under 5 presets — see the root [`README.md`](../README.md) for
the full product-level explanation of how ranking works.

### Three source modes

| Mode | What it is | How it enters | Ranking |
|---|---|---|---|
| `official_automated` | official carrier data fetched automatically | `metromobile refresh <slug>` (Chatr) | rankable when verified + fresh |
| `official_manual` | official public data a person can view but bots can't | `metromobile import` with a capture + transcribed plans + operator + timestamp | rankable when verified + **within the strict re-verify window**; past it → `stale`, not rankable until re-verified |
| `trusted_secondary` | reputable third-party aggregator | `metromobile refresh whistleout` (one aggregator adapter emits plans for many carriers), or `metromobile import --mode trusted_secondary` | **never** `verified` or rankable on its own — `secondary_confirmed`, confidence-capped at 0.6; rankable only if an official cross-check exists or `METROMOBILE_SECONDARY_RANKING_ALLOWED=true` |

Connected today: **Chatr** (`official_automated`) and **Bell / Koodo / Freedom
Mobile** (`official_manual`) — together the current V1 dataset. **WhistleOut
Canada** (`trusted_secondary`, its robots-permitted "popular plans" widget → a
rotating handful of plans for Bell / Public Mobile / Fido / Chatr / 7-Eleven
SpeakOut) is implemented and covered by tests but is **not** part of the
current live V1 dataset. Fizz is deliberately excluded — its robots.txt blocks
AI bots (`ai-train=no`).

We never bypass Cloudflare, CAPTCHAs, auth, anti-bot, or private APIs. LLMs are
not a source — they may only normalize text from an identified real source.

Registered but not automatically fetchable (the registry documents *why*, and
they can be brought in via `official_manual` import):

| Provider | Why not automated |
|---|---|
| Public Mobile | whole site behind a Cloudflare anti-bot challenge |
| Freedom Mobile | only public data is an unfiltered ~415-row internal ratebook |

## Setup

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env            # optional — defaults work as-is
```

## Create the database

SQLite (default):

```bash
.venv/bin/alembic upgrade head      # or: .venv/bin/metromobile init-db
```

PostgreSQL: set `METROMOBILE_DATABASE_URL=postgresql+psycopg://…` in `.env`
(install a driver, e.g. `pip install "psycopg[binary]"`), then `alembic upgrade head`.

## Reproduce the full V1 dataset

```bash
.venv/bin/metromobile bootstrap
```

Idempotently reconciles the database to the approved V1 dataset —
`fixtures/ranking/v1_dataset.json` — through the normal import pipeline: Bell,
Koodo, and Freedom Mobile via `official_manual` import, Chatr via an
`official_automated` refresh of the committed snapshot. Safe to re-run: each
provider is only (re-)imported if it's missing or short, so it also repairs a
partially-populated database. This is distinct from `refresh chatr` below,
which touches only the one provider and is for iterating on the Chatr adapter
during development.

## Refresh the data (manual, development)

```bash
.venv/bin/metromobile refresh chatr
```

Fetches the official page, stores an immutable raw document under `raw_store/`,
parses + normalizes + validates, and upserts the plans. Re-run any time; reload
the website to see the result. To re-parse a saved capture instead of hitting the
network:

```bash
.venv/bin/metromobile refresh chatr --fixture fixtures/chatr/plans_page.html
```

### Import an `official_manual` / `trusted_secondary` carrier

For a carrier whose official plans a person can view but automated retrieval is
blocked: the operator saves the rendered official page and writes a small
manifest of the plan fields they read off it. Both are kept — the capture as
immutable evidence, the manifest as the transcribed data.

```bash
.venv/bin/metromobile import \
  --manifest captures/publicmobile/2026-09-03.json \
  --capture  captures/publicmobile/2026-09-03.html \
  --operator devvrat \
  --verified-at 2026-09-03T14:00:00Z          # optional; defaults to now (UTC)

# reputable third party instead of the carrier's own page:
.venv/bin/metromobile import ... --mode trusted_secondary [--crosscheck]
```

The official source URL lives in the manifest (`source.url`).

Manifest shape (see `fixtures/manual_example/manifest.json`):

```json
{
  "provider": {"slug": "...", "display_name": "...", "network": "...", "plan_model": "..."},
  "source":   {"url": "https://...", "kind": "capture"},
  "plans": [{
    "external_id": "...", "plan_name": "...",
    "monthly_price_cad": 45, "regular_price_cad": 55, "price_period": "monthly",
    "promo_price_cad": 45, "promo_savings_cad": 10,
    "promo_ends_at": "2026-10-31T00:00:00Z", "promo_expiry_known": true,
    "promo_new_customers_only": true, "promo_online_only": true,
    "data_total_gb": 30, "data_unlimited": false, "network_technology": "5G",
    "plan_type": "postpaid", "byod": true, "contract_required": false,
    "canada_wide_calling": true, "unlimited_text": true, "availability": "online"
  }]
}
```

Any `NormalizedPlan` field is accepted; unrecognized keys are kept under the
plan's `attributes`, not dropped. Record only what the page states — missing
fields are stored `null`, never guessed.

**Ready-to-use kits** for Bell, Koodo, Freedom Mobile and Rogers live in
`imports/<carrier>/` — each has the exact BC plans URL, a `manifest.template.jsonc`,
and a `CAPTURE.md` with the region/toggle steps and carrier-specific pitfalls.
Start with `imports/README.md`.

### Auto-drafting a manifest (Bell)

```bash
.venv/bin/metromobile draft-manifest bell --capture imports/bell/captures/2026-09-06.mhtml
```

Reads the saved capture and writes `…/2026-09-06.plans.jsonc` pre-filled with
every plan + field it can confidently read (`.mhtml` and `.html`; not `.pdf`).
It never fetches or invents — unclear fields stay `null`, and each plan carries a
`_review` block with the source text of every auto-filled value. The file is
marked `_draft.reviewed = false`; **`import` / `reverify` refuse it** until a
human checks it against the page and sets `"reviewed": true` (or deletes the
`_draft` block). If extraction isn't reliable it raises a clear error and you
fall back to the blank template. Only `bell` is wired so far.

### Re-verifying (`metromobile reverify`)

```bash
.venv/bin/metromobile reverify \
  --manifest imports/bell/captures/2026-11-01.plans.jsonc \
  --capture  imports/bell/captures/2026-11-01.mhtml \
  --operator you --note "quarterly re-check"
```

Prints a **per-plan field diff** (stored vs. new), then appends a new immutable
`RawDocument` + new `plan_verification_events` rows — the previous capture, the
previous observed values, and who/when are **never overwritten**. A plan that has
vanished from the carrier's lineup is marked `invalid` with a `vanished` event,
not deleted. `metromobile provenance <plan-id>` shows a plan's full history.

Manifests may be `.json` or `.jsonc` (`//` and `/* */` comments, trailing commas).

### Expire stale data

```bash
.venv/bin/metromobile sweep     # marks anything past its re-verify window stale + non-rankable
```

The API also enforces this at read time, so stale data is never served as current
even if `sweep` hasn't run.

### Inspect

```bash
.venv/bin/metromobile providers          # per-provider: mode, plan count, freshness
.venv/bin/metromobile plans
.venv/bin/metromobile runs
.venv/bin/metromobile provenance <plan-id>   # full verification history for one plan
```

## Run the API

```bash
.venv/bin/metromobile serve            # http://127.0.0.1:8000
```

* `GET /api/plans?municipality=<id>` → `{ meta, plans[], scores[], profiles[] }`
  (`scores`/`profiles` are always empty here — ranking is served separately by
  `/api/rank` below). Each plan carries its `source_mode`, `verification_method`,
  `verified_by`, effective `verification_status` (staleness enforced here),
  `freshness`, and `verification_event_count`. Plans are national / province-wide;
  the municipality is echoed back but does not change results, and no location
  differences are invented.
* `GET /api/rank?preset=<preset>&municipality=<id>&...` → a ranked Top-N for
  one of the 5 presets, with the optional V1 customization filters (budget,
  min data, plan type, 5G, roaming, student/AutoPay context) applied. See
  `ranking.py` and the root `README.md` for how scoring works.
* `GET /api/meta?municipality=<id>` → the `meta` block only (cheap freshness poll).
* `GET /health` (alias: `GET /healthz`)

## Tests

```bash
.venv/bin/pytest
```

`tests/test_chatr_parser.py` pins the parser to `fixtures/chatr/plans_page.html`
+ `fixtures/chatr/expected_normalized.json`. If Chatr changes its page structure
the parser raises `ParseError` (the refresh fails loudly and the last good data
stays) and the snapshot test fails — the signal to re-capture the fixture and
re-check the field mapping.

`tests/test_source_modes.py` covers all three modes: automated tagging, manual
import + immutable evidence, secondary restrictions, manual data going stale and
losing ranking eligibility, re-verify appending history without overwriting, and
Chatr staying intact alongside a manual import.

`tests/test_ranking.py` covers the ranking engine (all 5 presets, component
scoring, customization filters); `tests/test_bootstrap.py` covers `bootstrap`
reproducing and repairing the approved V1 dataset.

## Freshness & ranking-eligibility

Every plan keeps: `source_mode`, `source_url`, `verification_method`,
`verified_by`, `last_verified_at`, `confidence`, `verification_status`, plus an
append-only `plan_verification_events` history and a link to its immutable
`RawDocument`.

`freshness` (`fresh` / `aging` / `stale`) uses windows chosen by source mode:

| Setting (`METROMOBILE_…`) | Default (hrs) | fresh → aging → stale | Applies to |
|---|---|---|---|
| `FRESH_HOURS` / `AGING_HOURS` | 6 / 24 | 6 h / 24 h | `official_automated` (scheduled) |
| `MANUAL_FRESH_HOURS` / `MANUAL_REVERIFY_HOURS` | 168 / 336 | 7 d / 14 d | `official_manual` (operator capture) |
| `SECONDARY_FRESH_HOURS` / `SECONDARY_REVERIFY_HOURS` | 12 / 36 | 12 h / 36 h | `trusted_secondary` |
| `SECONDARY_CONFIDENCE_CAP` | 0.6 | — | secondary confidence ceiling |
| `SECONDARY_RANKING_ALLOWED` | `false` | — | let secondary-only plans rank |

A **verified promo expiry overrides the capture clock**: an expired promotion
stops being a current offer (price reverts to regular) immediately — see
`pricing.py` — no matter how young the capture is.

`verification_status` per mode:

* `official_automated` — complete + not stale → `verified` (rankable)
* `official_manual` — complete + within re-verify window → `verified` (rankable);
  past it → `stale` (not rankable until re-imported)
* `trusted_secondary` — complete + fresh → `secondary_confirmed` (not rankable);
  with `official_crosscheck` → `verified` (rankable); confidence ≤ the cap
* any mode — missing rankable fields → `provisional`; failed hard checks or
  vanished from source → `invalid`

A stale / `invalid` / `provisional` / `secondary_confirmed` plan is dropped from
the meta "current plan" count and flagged in the UI. `is_rankable` is only true
when the factual fields a future ranking engine must not guess are all present
(name, effective price, data allowance / unlimited status, plan type,
availability, source, verification timestamp). Missing → the plan is stored and
shown, but held out of ranked results with its issues listed.

**Restricted-eligibility offers.** A plan with `eligibility_restricted = true`
(partner / employer / exclusive / invite-only) is a real, `verified` plan but
`is_rankable` is forced **false** — the default Top-N must not offer a price an
ordinary user can't get. It stays queryable/displayable, with
`eligibility_conditions` naming what would qualify a user; an eligibility-aware
ranking mode can include it for a user known to meet the condition.

## Plan schema

`NormalizedPlan` / the `plans` table carry every factual field the future ranking
profiles and user-preference filtering will need — populated only when the
official source actually states it, otherwise `NULL` (never inferred):

* **pricing tiers** — `regular_price_cad` (the **unconditional** price — the only one a neutral ranking uses), `autopay_price_cad` + `autopay_conditions` (**only** when a pure AutoPay-only price is separately stated — if AutoPay is bundled with a promo/new-activation credit that the carrier doesn't itemise, the figure is a conditional `promo_price_cad`, not an AutoPay price), `bundle_price_cad` + `bundle_conditions` (needs a home-Internet/streaming bundle), `promo_price_cad` + `promo_conditions` + `promo_stacks_conditions`, `pricing_notes` (raw observed `[{amount,label}]`), plus legacy `price_cad` / `monthly_price_cad`, `price_period`, `term_months`. A plan with **only** conditional prices is stored and shown but **not rankable** until the unconditional price is added.
* **promotion** — `promo_name`, `promo_savings_cad`, `promo_starts_at`, `promo_ends_at`, `promo_expiry_known`, `promo_duration_months`, `promo_new_customers_only`, `promo_online_only`, `promo_autopay_required`, `promo_source_url`
* **fees / contract / device** — `activation_fee_cad`, `activation_fee_waived`, `contract_required`, `contract_length_months`, `byod`, `byod_required`, `device_restrictions`
* **data** — `data_base_gb`, `data_bonus_gb`, `data_promo_gb`, `data_total_gb`, `data_full_speed_gb`, `data_unlimited`, `data_unlimited_is_full_speed`, `data_hard_cap`, `throttle_speed`, `overage_note`, `overage_rate_per_gb_cad`, `data_rollover`
* **network** — `network_technology` (`5G+`/`5G`/`4G LTE`/`4G`/`3G`), `network_speed_tier`, `max_download_mbps`, `has_5g`
* **calling / travel** — `plan_type`, `canada_wide_calling`, `unlimited_text`, `international_text`, `includes_us`, `includes_mexico`, `us_mex_data_gb`, `international_roaming`
* **features** — `hotspot`, `hotspot_data_gb`, `esim`, `wifi_calling`, `autopay_required`
* **student** — `student_plan`, `student_offer`, `student_eligibility_note` (a "Best for Students" ranking will favour real characteristics; a *student offer* is only shown as one when its eligibility is verified)
* **restricted eligibility** — `eligibility_restricted`, `eligibility_conditions` (see the ranking-eligibility section above)
* **geography** — `available_regions` (only when the source states a restriction), `geo_availability_note`

### Pricing tiers & current offers (`metromobile/pricing.py`)

Every discount Bell-style pricing bakes into a headline number is stored as its
own tier with its own conditions. At serve time `price_view()` computes:

* `universal_price_cad` — the unconditional (`regular_price_cad`) price; what a
  neutral ranking uses. `None` when only conditional prices are on record.
* `display_price_cad` — shown by default; **never** a conditional price presented
  as universal. Falls back to the highest *known* priced tier when the
  unconditional price is missing, with a `price_note`.
* `best_case_price_cad` — the lowest a customer could pay meeting every condition
  (+ an active promo).
* `price_tiers` — cheapest-first `[{amount, label, conditions[]}]`.
* `effective_price_cad`, `is_current_offer`, `offer_active`, `offer_expired`,
  `offer_savings_cad`, `offer_is_conditional`.

A `$50` plan that needs Internet + AutoPay + a promo does **not** read as a
universally available `$50` plan — `universal_price_cad` stays at the
unconditional figure (or `None`). **An expired promotion is never a current offer
and its price never counts** — the plan reverts to its regular price. If the
expiry is unknown that fact is surfaced (`promo_expiry_known = False/None` +
a validation warning), not guessed. `meta.current_offer_count` counts the plans
that are a current offer right now.

## Layout

```
metromobile/
  config.py          settings (env-driven, SQLite default)
  db.py  models.py    schema + engine  (Plan, RawDocument, PlanVerificationEvent, …)
  normalize.py        "10 GB" → 10.0, price parsing (never guesses)
  validation.py       hard errors + per-mode ranking-eligibility gate + promo checks
  pricing.py          price tiers (regular vs autopay vs bundle vs promo) + current-offer logic
  freshness.py        fresh / aging / stale, per source mode
  pipeline.py         run_refresh (automated) · run_manual_import (manual/secondary) · sweep_stale
  ranking.py          deterministic ranking engine — 5 presets, 6 scored components
  providers/
    base.py           AutomatedAdapter / ManualAdapter / SecondaryAdapter, NormalizedPlan, ParseError
    chatr.py          official_automated adapter (server-rendered JSON)
    whistleout.py     trusted_secondary adapter (one aggregator -> many carriers)
    public_mobile.py  stub — Cloudflare block; import via official_manual
    freedom_mobile.py stub — ratebook problem; import via official_manual
  serializers.py      ORM → API shapes (recomputes staleness at serve time)
  api.py              FastAPI app
  cli.py              `metromobile` commands
fixtures/chatr/           committed snapshot for the parser test
fixtures/manual_example/  schema-demo manifest + capture (tests only, NOT a real carrier)
fixtures/ranking/v1_dataset.json   the reviewed V1 dataset `bootstrap` reconciles the DB to
raw_store/                immutable fetched documents + manual captures (gitignored)
```
