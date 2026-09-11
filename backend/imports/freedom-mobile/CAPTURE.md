# Freedom Mobile — capture guide

**Network:** Freedom (Videotron / Quebecor) · **Model:** postpaid (BYOP) · **slug:** `freedom-mobile`
**Source mode:** `official_manual` — the plan grid on `shop.freedommobile.ca` is
client-rendered (the served HTML has no plan prices). Freedom's only public
endpoint, `api.freedommobile.ca/api/v1/plans`, returns an **unfiltered ~415-entry
internal ratebook** (legacy plans, duplicates, prepaid/existing-customer/"MB"
variants, "6 Month" legacy offers) with no field that identifies the current
curated BC consumer list — picking "current plans" from it would be selection =
fabrication. So: operator capture → `draft-manifest` → review → import, like
Bell / Koodo.

## 1. Open the page

<https://www.freedommobile.ca/en-CA/plans>  (redirects to
`shop.freedommobile.ca/en-CA/plans`)

* **Region → British Columbia.** Freedom's site **defaults to Ontario** (it sets
  a `region=ON` cookie) and Freedom has **regional pricing/availability**. Use
  the region / province picker (or enter a Metro Vancouver postal code, e.g.
  `V6B 1A1`) and confirm the page shows **British Columbia** before reading any
  prices. This is the single most important step.
* Choose the **Bring Your Own Phone** view — there's a tab / toggle near the plan
  grid on `shop.freedommobile.ca/en-CA/plans`. (The deeper
  `.../plans/bring-your-own-phone` URL is not a reliable public landing page —
  it can render "Sorry, something went wrong" — so the stored official source is
  the top-level `/en-CA/plans` page.) Avoid the "MyTab" / "with a phone" /
  financing view.
* **Digital Discount toggle:** Freedom's headline price is usually
  "$X/mo after Digital Discount" (–$5/mo, requires **AutoPay + eBill**). If
  there's a toggle for it, leave it in its **default** state and note which state
  that is — if both the with- and without-discount numbers show on each card, the
  capture keeps both.
* **Do not log in** and don't start a checkout. The region picker (or postal
  code) is enough.

## 2. Scroll so every plan renders

The plan cards load client-side and some are lazy. **Scroll slowly through the
whole plan grid**, wait a second at the bottom, and click any "see all plans" /
"show more" / "compare plans" control so every card and price is rendered.
If there's a "Total Freedom" vs "Big Gig" / "Nationwide" section split, make sure
both are expanded.

## 3. Save the page

`File → Save Page As…` → **"Web Page, Single File"** →
**`imports/freedom-mobile/captures/<YYYY-MM-DD>.html`** (a simple name — do **not**
type a path with `/` in the Save dialog). "Web Page, Complete" also works. If it
lands in `~/Downloads`, tell me the filename and I'll move it.

Freedom **prepaid** plans are a separate page (`…/en-CA/prepaid-plans`) — this kit
is the **postpaid BYOP** page only.

## 4. Auto-draft, then review

```bash
cd backend
.venv/bin/metromobile draft-manifest freedom-mobile --capture imports/freedom-mobile/captures/<YYYY-MM-DD>.html
```

Writes `<capture>.plans.jsonc` — one plan object per plan, every value it could
read pre-filled, the rest `null`, `_draft.reviewed: false`. Nothing is imported.
Review it against the page, fill the `null`s the page clearly answers, set
`"_draft": { "reviewed": true }`, then import.

## 5. What each plan needs (verify / fill)

| field | rule |
|---|---|
| `plan_name` | exact card title, **including** the "+ Roam Beyond XGB" suffix, e.g. `Total Freedom 100GB + Roam Beyond 5GB` |
| `regular_price_cad` | the **unconditional** monthly price — no Digital Discount, no promo. If the card only shows the discounted / promo number, leave `null` (the plan then isn't rankable until confirmed) |
| `promo_price_cad` | a lower **limited-time** price, if the page frames it as one |
| `promo_name` / `promo_ends_at` / `promo_expiry_known` | `promo_expiry_known` = `false` unless a real end date is printed; then set the date + `true` |
| `promo_duration_months` | "$X/mo for 24 months" style |
| `autopay_price_cad` / `autopay_discount_cad` | the **Digital Discount** price / amount when its *only* condition is AutoPay + eBill (e.g. `autopay_discount_cad: 5`). If the discounted price mixes a promo + Digital Discount that Freedom doesn't itemise, treat it as `promo_price_cad` with the conditions spelled out (same rule as Bell / Koodo) |
| `autopay_required` / `autopay_note` | `true` + "$5/mo Digital Discount requires AutoPay + eBill" if the headline needs it |
| `data_full_speed_gb` / `data_base_gb` | the **DOMESTIC** full-speed data only — **never** include the Roam Beyond number |
| `data_bonus_gb` / `data_promo_gb` | a limited-time bonus GB amount, kept **separate** from base |
| `data_unlimited` / `data_unlimited_is_full_speed` / `throttle_speed` | Freedom typically slows data after the allowance (no hard stop). If the card says so: `data_unlimited: true`, `is_full_speed: false`, `throttle_speed` from the text (e.g. `"512 Kbps"`). If it doesn't say → leave `null`, don't assume |
| `data_hard_cap` / `overage_note` | `data_hard_cap: false` + "no overage fees; data slows after the allowance" **only if the page states it** |
| `us_mex_data_gb` | the **Roam Beyond** GB amount goes here (Roam Beyond covers the US, Mexico + other destinations) — it is **roaming** data, stored separately from domestic |
| `international_roaming` / `international_roaming_note` | `true` + "Roam Beyond: X GB/mo of roaming data in the US, Mexico and N destinations" (use Freedom's own wording / count) |
| `includes_us` / `includes_mexico` | `true` **only** for a plan explicitly sold as "Canada-U.S." or "Canada-US-Mexico" (talk/text/data in-country, not roaming). Roam Beyond alone does **not** set these |
| `network_technology` / `has_5g` / `max_download_mbps` | "5G" / "5G+" / "4G LTE" badge; any "up to X Mbps" |
| `plan_type` | `postpaid` (this page) |
| `canada_wide_calling` / `unlimited_text` / `international_text` | "Unlimited Canada-wide talk", "Unlimited global text" etc. — `true` only if stated |
| `hotspot` / `hotspot_data_gb` / `hotspot_note` | if the card mentions mobile hotspot / tethering |
| `activation_fee_cad` | Freedom SIM / connection / setup fee **only** if explicitly shown on this page; else `null` |
| `contract_required` / `contract_length_months` | only if the page states a term; **do not** assume `false` |
| `byod` (true) / `byod_required` | this is the BYOP page |
| `eligibility_restricted` / `eligibility_conditions` | any "exclusive" / "partner" / "targeted" / "existing customers" / invite-only offer → `true` + the condition; the ranking then excludes it from the default Top 5 |
| `available_regions` | `["BC"]` only if the plan is explicitly BC-only; else `null` |

## 6. Freedom pitfalls

* **Domestic data ≠ Roam Beyond data. Never add them.**
  `Total Freedom 100GB + Roam Beyond 5GB` = **100 GB domestic**, **5 GB roaming**.
  100 → `data_full_speed_gb` / `data_base_gb`; 5 → `us_mex_data_gb` +
  `international_roaming: true` + note. Storing `105` would be wrong.
* **Freedom Network vs Nationwide.** Some plans split domestic data
  ("50 GB Freedom Network + 1 GB Nationwide"). Record what the card states and
  describe the split in `conditions` — don't silently merge.
* **Digital Discount is conditional.** The "after Digital Discount" price needs
  AutoPay + eBill. Only put a figure in `autopay_price_cad` if that's its sole
  condition; if it's mixed with a promo, it's `promo_price_cad` with the
  conditions. Neutral ranking uses `regular_price_cad`.
* **Roaming country claims.** Only record the countries / destination count
  Freedom's own text states for Roam Beyond. Don't generalise "US + Mexico" to
  "and 100 more" unless the page says so.
* **Unlimited-after-throttle.** Set `data_unlimited` / `throttle_speed` only from
  explicit wording. If the card just says "100 GB" with no "then slows"
  statement, leave `data_unlimited` null.
* **Multi-line / family pricing.** Freedom pushes "$25/mo on line 3+". Ignore —
  single-line price only.
* **Legacy / promo mix.** The grid mixes permanent plans with "limited time"
  promo-priced or bonus-data plans. Limited-time → `promo_price_cad` +
  `promo_expiry_known` (false unless a date is shown).
* **Nothing inferred.** If the page doesn't clearly establish a value, `null`.

## 7. Import (after the draft is reviewed)

```bash
cd backend
.venv/bin/metromobile import \
  --manifest imports/freedom-mobile/captures/<YYYY-MM-DD>.plans.jsonc \
  --capture  imports/freedom-mobile/captures/<YYYY-MM-DD>.html \
  --operator <your-name>
```

Omit `--verified-at` for a capture saved today. A Freedom capture stays current
for 7 days, ages after that, goes stale + ranking-ineligible after 14 —
re-import a fresh capture with `metromobile reverify` to restore it.
