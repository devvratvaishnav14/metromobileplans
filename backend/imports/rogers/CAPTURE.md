# Rogers — capture guide

**Network:** Rogers · **Model:** postpaid · **slug:** `rogers`

## 1. Open the page

<https://www.rogers.com/plans>

* Rogers wireless pricing is largely **national**; there is usually no province
  selector on the plans page. If a location/region banner appears, set it to
  **British Columbia** or a BC postal code.
* Switch the plan view to **"Bring your own phone"** / **"SIM only"** if it
  defaults to "with a phone" (financing) pricing — a tab or filter above the
  plan grid.
* Rogers shows the **"with automatic payments"** price by default (a ~$10/mo
  discount). Keep it on, set `autopay_required: true`, and if the non-autopay
  price is shown put it in `regular_price_cad`.

## 2. Save the page

`File → Save Page As… → "Web Page, Single File" (.mhtml)`
→ `imports/rogers/captures/YYYY-MM-DD.html`

## 3. What to capture, per plan

Rogers' consumer lineup is mostly **"5G Infinite"** unlimited-data plans
(e.g. "5G Infinite Premium 100GB", "5G Infinite Essential 50GB"), sometimes a
cheaper tiered plan.

| field | where | notes |
|---|---|---|
| `plan_name` | plan card title | exact, e.g. `5G Infinite Premium 100GB` |
| `monthly_price_cad` | headline `$__/mo` | with-automatic-payments price |
| `regular_price_cad` | "without automatic payments $__" if shown | else `null` |
| `autopay_required` / `autopay_note` | `true` + the wording | |
| `data_total_gb` / `data_full_speed_gb` | "100GB at fast LTE/5G speed" | the full-speed bucket |
| `data_unlimited` | `true` — "Infinite" data continues after the bucket | |
| `data_unlimited_is_full_speed` | `false` — reduced speed (usually 512 Kbps) after the bucket | |
| `throttle_speed` | `"512 Kbps"` if stated | fine print |
| `data_hard_cap` | `false` for Infinite plans | |
| `network_technology` / `has_5g` | "5G" badge | |
| `canada_wide_calling` / `unlimited_text` | "Unlimited talk & text" | |
| `includes_us` / `includes_mexico` | ONLY for a plan that explicitly says Canada/US or Canada/US/Mexico **data or calling** (some Premium tiers) | `us_mex_data_gb` if a shared amount is given |
| `international_roaming` | `true` if the plan bundles a roaming pass / "Roam Like Home" allowance | |
| `data_promo_gb` / `promo_*` | "Get 30GB bonus / $__/mo for 24 months, limited time" | see pitfalls |
| `activation_fee_cad` | Rogers Connection/Setup Fee (~$60) — footnote / checkout | `null` if not on the page |
| `available_regions` | `null` — Rogers plans are national | |

## 4. Rogers pitfalls

* **Automatic payments discount.** The big number already has the ~$10/mo
  autopay discount. `monthly_price_cad` = that number, `autopay_required: true`;
  non-autopay price (if shown) → `regular_price_cad`.
* **"5G Infinite" = unlimited-then-slow, not a hard cap.** Bucket at full speed,
  then 512 Kbps. `data_unlimited: true`, `data_unlimited_is_full_speed: false`,
  `data_hard_cap: false`.
* **Intro pricing.** "$__/mo for 24 months, then $__/mo." → `promo_price_cad` =
  the intro price, `regular_price_cad` = the after price, `promo_duration_months:
  24`, `promo_expiry_known` per whether an actual end date is given.
* **Bonus data.** "Get 30GB extra, limited time" → `data_promo_gb: 30` +
  `promo_expiry_known: false` (unless dated). The permanent allowance is the base
  number.
* **Additional-line / family pricing.** Capture the single/first-line price only.
* **Device financing view.** If you didn't switch to Bring-your-own-phone, the
  monthly figure bundles a device payment. Re-check the toggle.
* **Rogers Mastercard / Rogers Bank perks.** "Save an extra 1–2% with the Rogers
  Mastercard" is a payment-method rebate — note it in `conditions` at most, don't
  change the price.
* **Connection Fee.** Real (~$60) but usually checkout-only. `null` if not on the
  plans page — don't guess.

## 5. Import

```bash
cd backend
.venv/bin/metromobile import \
  --manifest imports/rogers/captures/YYYY-MM-DD.plans.jsonc \
  --capture  imports/rogers/captures/YYYY-MM-DD.html \
  --operator <your-name> \
  --verified-at 2026-09-07T12:00:00Z
```
