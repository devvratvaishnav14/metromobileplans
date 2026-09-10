# Manual official-import kits

`official_manual` = an official carrier page a person can view in a normal browser
but that blocks automated retrieval. You (the operator) open the page, save it as
evidence, transcribe the plan facts into a manifest, and run `metromobile import`.
Nothing is scraped; nothing is invented.

## Order of work

**Do Bell first.** Prove the workflow end-to-end with one carrier, confirm it
appears correctly beside Chatr on the website, then repeat for Koodo, Freedom and
Rogers. The kits for all four are ready, but only Bell is being captured now.

Kits here: **bell**, **koodo**, **freedom-mobile**, **rogers**. Each folder has:

| file | what it is |
|---|---|
| `CAPTURE.md` | the exact URL, region/toggle steps, field-by-field capture notes, and the pitfalls for that carrier |
| `manifest.template.jsonc` | a skeleton with the provider block filled and one fully-commented example plan to duplicate |
| `captures/` | where your saved page + filled manifest go (git-ignored) |

## The workflow (same for every carrier)

1. **Open** the carrier's plans URL (in `CAPTURE.md`) in your normal browser.
2. **Set the region** to British Columbia if the page shows a region selector or
   indicator. If pricing is national, note that.
3. **Switch to "Bring your own phone" / "SIM only"** if the page defaults to
   device-financing pricing.
4. **Note the autopay state** — most carriers show the "with automatic payments"
   price by default. Record which price you captured and whether autopay is
   required for it.
5. **Save the page** as evidence. In Chrome: `File → Save Page As…` →
   **"Web Page, Single File"** → `imports/<carrier>/captures/2026-09-06.mhtml`
   (today's date; **keep the `.mhtml` extension**). "Web Page, Complete" (`.html`)
   and Print → PDF (`.pdf`) also work. The pipeline records the file for what it
   is — an `.mhtml` is stored as `multipart/related`, never disguised as HTML.
6. **Get a manifest to review.**
   * **Bell:** `metromobile draft-manifest bell --capture imports/bell/captures/2026-09-06.mhtml`
     pre-fills `…/2026-09-06.plans.jsonc` from your capture. Open it, check every
     value against the page (each plan's `_review` block shows what was
     auto-filled and its source text), fill the `null`s the page clearly answers,
     then set `"_draft": { "reviewed": true }`. `import` refuses it until then.
   * **Koodo / Freedom / Rogers:** no auto-drafter yet — copy
     `manifest.template.jsonc` to `captures/YYYY-MM-DD.plans.jsonc` and fill one
     plan object per plan by hand.

   Either way: **only set a field if the official page clearly states it; leave
   anything unclear as `null`.** Do not use WhistleOut or any other site to fill
   gaps.
7. **Import**:

   ```bash
   cd backend
   .venv/bin/metromobile import \
     --manifest imports/<carrier>/captures/2026-09-06.plans.jsonc \
     --capture  imports/<carrier>/captures/2026-09-06.mhtml \
     --operator <your-name>
   ```

   `--verified-at` is **optional**: omit it and the import records "verified now".
   Pass `--verified-at 2026-09-01T14:00:00Z` only when importing an older capture.

8. **Reload the website.** Complete plans appear under "Verified &
   ranking-eligible", tagged `official_manual`, "Verified by \<your-name\>".
   Incomplete ones show under "Secondary / not officially verified" as
   `provisional` until you fill the missing rankable fields.

`.jsonc` = JSON with `//` full-line comments (the template's notes). Plain `.json`
also works.

## Re-verifying later (no history is lost)

Carrier prices and promos change. To re-check a carrier:

1. Repeat steps 1–6 with a **new date**.
2. Run **`metromobile reverify`** (instead of `import`):

   ```bash
   .venv/bin/metromobile reverify \
     --manifest imports/<carrier>/captures/2026-11-01.plans.jsonc \
     --capture  imports/<carrier>/captures/2026-11-01.html \
     --operator <your-name> \
     --note "quarterly re-check; Bell dropped the 100GB tier"
   ```

`reverify` prints a **per-plan field diff** (what changed vs. what's stored), then:

* writes a **new** immutable `RawDocument` for the new capture (the old capture
  file and DB row stay);
* appends **new** `plan_verification_events` rows — the previous observations
  (old price, old data, old promo, who verified, when) are never overwritten;
* updates each `Plan` row to the latest values and re-runs validation;
* any plan that's gone from the carrier's lineup is marked `invalid` (with a
  `vanished` history event) — it is **not** deleted.

`metromobile provenance <plan-id>` shows a plan's full history — every capture,
price, operator and timestamp. `plan-id` comes from `metromobile plans`.

## The freshness clock

An `official_manual` capture is:

| age | state |
|---|---|
| **0–7 days** | current / verified |
| **7–14 days** | aging — a warning shows, still ranking-eligible |
| **> 14 days** | stale — drops out of ranking eligibility until you `reverify` |

Configurable via `METROMOBILE_MANUAL_FRESH_HOURS` (default 168) and
`METROMOBILE_MANUAL_REVERIFY_HOURS` (default 336) in `.env`.

**Promo expiry overrides the capture clock.** If a plan's promotion has a
verified explicit end date, that offer stops being treated as current the moment
it expires — the price reverts to regular — even if the capture is only a day
old. Automated sources (Chatr) keep their much shorter windows (6 h / 24 h).
