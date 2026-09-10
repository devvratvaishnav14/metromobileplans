# Koodo — capture guide

**Network:** TELUS · **Model:** postpaid (BYOP) · **slug:** `koodo`
**Source mode:** `official_manual` — Koodo's plan grid is rendered by a
client-side micro-frontend that pulls prices from a session-scoped BFF proxy
(`/shop/api/proxyRatePlanSelectionBff`). There is **no public plan feed** in the
page HTML (the served HTML contains zero prices / GB values), and the BFF proxy
needs a live browser session, so it can't be used as `official_automated`
without replaying session tokens (which we do not do). So: operator capture →
`draft-manifest` → review → import, exactly like Bell.

## 1. Open the page

<https://www.koodomobile.com/en/plans>
(redirects to `…/en/shop/mobility/plans/bring-your-own-phone`)

* **Region → British Columbia.** Look for the region / province control (often
  top-right, "Change region", or a postal-code prompt). Confirm it reads BC
  before you read any prices — Koodo pricing can differ by province.
* You should land on **"Bring your own phone"** already. If it shows "Choose a
  phone" / financing / Tab pricing, switch to **Bring your own phone / SIM-only**.
* **Pre-Authorized Payment / AutoPay toggle:** if the grid has a toggle for
  "prices with Pre-Authorized Payment" (a.k.a. PAP / AutoPay / Digital Discount),
  leave it in its **default** state and just note which state that is. Don't flip
  it — if Koodo shows both a with-PAP and a without-PAP number on each card, the
  capture keeps both.
* **Do not log in.** Don't enter a real address if it forces an account flow —
  the region selector is enough. If a plan says "not eligible" for your area,
  that's fine, capture it anyway.

## 2. Scroll so every plan renders

The plan cards load lazily. **Scroll slowly through the whole plan grid**
(top to bottom) and wait a second at the bottom so every card and its price has
rendered. If there's a "show more plans" / "see all plans" control, click it.

## 3. Save the page

`File → Save Page As…` → **"Web Page, Single File"** →
save as **`imports/koodo/captures/<YYYY-MM-DD>.html`** (a simple name — do **not**
type a path with `/` into the Save dialog). "Web Page, Complete" (`.html` + a
`_files` folder) also works. If it lands in `~/Downloads`, just tell me the
filename and I'll move it.

Koodo has **prepaid** plans on a separate page (`…/en/prepaid-plans`). This kit
is the **postpaid BYOP** page only.

## 4. Auto-draft, then review

```bash
cd backend
.venv/bin/metromobile draft-manifest koodo --capture imports/koodo/captures/<YYYY-MM-DD>.html
```

Writes `<capture>.plans.jsonc` — one plan object per plan, pre-filled with every
value read off the capture, the rest `null`, `_draft.reviewed: false`. Nothing is
imported. Open it, check every value against the page, fill the `null`s the page
clearly answers, set `"_draft": { "reviewed": true }`, then import.

## 5. What each plan needs (verify / fill)

| field | where | rule |
|---|---|---|
| `plan_name` | card title | exact text, e.g. `Canada 60GB`, `Canada‑US 75GB` |
| `regular_price_cad` | the **unconditional** $/mo — no PAP, no promo | if the card only shows a with-PAP or promo price and never the plain one, leave **null** (the plan then isn't rankable until confirmed) |
| `monthly_price_cad` | the headline $/mo shown | the number in big type on the card |
| `promo_price_cad` | a lower **promotional** price, if shown as such | only if the page frames it as a limited-time / intro price |
| `promo_name` / `promo_ends_at` / `promo_expiry_known` | promo framing + fine print | `promo_expiry_known` = `false` unless a real end date is printed; then set the date + `true` |
| `promo_duration_months` | "$X/mo for the first 12 months" | the number |
| `autopay_price_cad` / `autopay_discount_cad` | a price/discount whose **only** condition is Pre-Authorized Payment | e.g. "$5/mo Digital Discount with PAP + eBill" → `autopay_discount_cad: 5` |
| `autopay_required` / `autopay_note` | `true` + the PAP wording if the headline price needs PAP | |
| `data_base_gb` / `data_full_speed_gb` | the **base** data at full speed | the number the plan permanently includes |
| `data_bonus_gb` / `data_promo_gb` | a **bonus** GB amount ("60GB + 15GB bonus, limited time") | keep this **separate** from base — never fold it into the base number |
| `data_total_gb` | a genuine **hard total cap** (data stops / pay-per-use at the cap, no throttle-and-continue) | set **only** for a hard cap; leave `null` for "unlimited after throttle" |
| `data_unlimited` / `data_unlimited_is_full_speed` / `throttle_speed` | "then unlimited at reduced speed" wording | if it throttles-and-continues: `data_unlimited: true`, `is_full_speed: false`, `throttle_speed` from the text |
| `data_hard_cap` / `overage_note` / `overage_rate_per_gb_cad` | "data stops" / "$X/100MB" / "pay-per-use" | |
| `network_technology` / `has_5g` / `max_download_mbps` / `network_speed_tier` | "5G" / "4G" badge + any "up to X Mbps" | copy exactly |
| `plan_type` | `postpaid` (this page) | |
| `canada_wide_calling` / `unlimited_text` | "Unlimited Canada-wide talk & text" | `true` only if stated |
| `includes_us` | **only** an explicit "Canada‑US" plan (US calling/data) | a plain "Canada" plan with US *texting* does **not** count |
| `includes_mexico` | only if stated (rare) | |
| `activation_fee_cad` | Koodo Connection Charge (~$60) — usually a footnote / checkout | `null` if not shown on this page — do not guess the amount |
| `byod` (true) / `byod_required` | this is the BYOP page | `byod_required: true` only if the plan is BYOD-only |
| `contract_required` / `contract_length_months` | only if the page states a term | **do not** assume `false` — leave `null` unless the page says "no contract" |
| `eligibility_restricted` / `eligibility_conditions` | any "exclusive" / "partner" / "targeted" / invite-only / employee offer | set `true` + the condition; the ranking then excludes it from the default Top 5 |
| `available_regions` | leave `null` unless the plan is explicitly BC-only | |
| `student_offer` / `student_plan` | only if this page shows a specific student plan/discount | otherwise `null` |

## 6. Koodo pitfalls

* **Bonus data vs base data.** Koodo constantly shows "75GB" that is really
  "60GB + 15GB bonus (limited time)". Base → `data_base_gb` / `data_full_speed_gb`;
  bonus → `data_bonus_gb` / `data_promo_gb`; set `promo_expiry_known`. Never
  record the inflated headline number as the permanent allowance.
* **Hard cap vs unlimited-after-throttle.** Many Koodo tiered plans are a hard
  cap (data stops or pay-per-use) — not "unlimited then slow". Read the card:
  hard cap → `data_hard_cap: true`, `data_unlimited: false`, `data_total_gb: <cap>`.
  Throttle-and-continue → `data_unlimited: true`, `data_unlimited_is_full_speed:
  false`, `data_total_gb: null`.
* **Pre-Authorized Payment.** If the headline price needs PAP, that's not the
  unconditional price. Only put a figure in `autopay_price_cad` if PAP is its
  *sole* condition; if it's mixed with a promo, treat it as `promo_price_cad`
  with the conditions spelled out (same rule we used for Bell).
* **Conditional promo pricing is not universal.** A "limited-time" or
  new-customer price goes in `promo_price_cad` with its conditions — the neutral
  ranking keeps using `regular_price_cad`.
* **"Canada‑US" only.** Only an explicit Canada‑US plan gets `includes_us: true`.
* **Koodo Tab** is device financing — irrelevant on a BYOP plan; not a fee or a
  contract.
* **Restricted / targeted offers** stay in the catalogue but out of the default
  ranking (`eligibility_restricted: true`).
* **Nothing inferred.** If the page doesn't clearly establish a value, leave it
  `null`.

## 7. Import (after the draft is reviewed)

```bash
cd backend
.venv/bin/metromobile import \
  --manifest imports/koodo/captures/<YYYY-MM-DD>.plans.jsonc \
  --capture  imports/koodo/captures/<YYYY-MM-DD>.html \
  --operator <your-name>
```

Omit `--verified-at` for a capture you saved today. A Koodo capture stays current
for 7 days, ages after that, and goes stale + ranking-ineligible after 14 —
re-import a fresh capture with `metromobile reverify` to restore it.
