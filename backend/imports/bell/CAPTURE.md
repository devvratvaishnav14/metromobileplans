# Bell — capture guide

**Network:** Bell · **Model:** postpaid · **slug:** `bell`

## 1. Open the page

<https://www.bell.ca/Mobility/Bring-Your-Own-Phone>

* If a **region** banner/selector appears, set it to **British Columbia**. Bell
  shows regional pricing; confirm the page says BC (`<meta name="province">` = BC,
  or a BC postal code is set).
* This is the Bring-Your-Own-Phone / SIM-only page. If it opens on a "with a new
  phone" / financing view, switch to BYOP.

### Bell shows pricing on two separate tabs — capture both

Near the "Rate plans" heading there are two tabs, each its **own page**:

* **Mobility only** (`.../Bring-Your-Own-Phone/Mobility_only.tab`) — pricing
  **without** a home-Internet / streaming bundle. This is the **primary**
  capture; its struck-through figure is the unconditional `regular_price_cad`
  (the rankable price) and its big price is the AutoPay tier.
* **With Streaming** (`.../Bring-Your-Own-Phone/With_Streaming.tab`) — the same
  plans with a streaming-bundle credit applied. Optional **second** capture;
  only its bundle price is used.

Every big `$__/mo.` on either tab bakes in credits (AutoPay, a new-activation
credit, and on the Streaming tab a $15 bundle credit). The **struck-through**
price next to it is the unconditional regular price — the same on both tabs.
Never record a big/credited price as the plan's universal price.

## 2. Save the pages (evidence)

In Chrome, on the **Mobility only** tab: `File → Save Page As…` → **"Web Page,
Single File"** → **`imports/bell/captures/<YYYY-MM-DD>.mobility-only.html`**
(or `.mhtml`). Then switch to **With Streaming** and save
**`<YYYY-MM-DD>.with-streaming.html`**.

Use a **simple filename** — never type a path with `/` into the Save dialog (the
browser turns it into one weird filename). If it lands in `~/Downloads`, move it
into `imports/bell/captures/` afterwards.

"Web Page, Complete" (`.html` + a `_files/` folder) also works — the drafter only
reads the `.html`. Avoid PDF. `.mhtml` is stored as `multipart/related`, not
disguised as HTML.

**Scroll the whole plan grid before you save** so every card is in the rendered
page.

## 3. Auto-draft the manifest, then check it

```bash
cd backend
.venv/bin/metromobile draft-manifest bell \
  --capture         imports/bell/captures/2026-09-07.mobility-only.html \
  --with-streaming  imports/bell/captures/2026-09-07.with-streaming.html
```

* `--capture` is the **primary** evidence — the **Mobility only** tab. Its
  struck-through figure becomes `regular_price_cad` (the unconditional,
  rankable price); its big price becomes `autopay_price_cad`.
* `--with-streaming` is optional — the **With Streaming** tab. Its big price
  becomes `bundle_price_cad`; its struck price is cross-checked against the
  primary's regular price (a mismatch is flagged, not silently merged).

This writes `<primary>.plans.jsonc` — one plan object per plan found, pre-filled
with every value it could read off your captures. Nothing is imported. It never
fetches anything or invents a value; unclear fields are left `null`.

Now **open that file and check it against the Bell page**:

* Fix any wrong value. The plan's `_review` block shows what was auto-filled and
  the `source_text` it came from.
* Fill the `null`s that the page clearly answers — `_review.check_these_nulls_…`
  lists the important ones. Use the field table + pitfalls below.
* When every plan is correct, set `"_draft": { "reviewed": true }` at the top of
  the file (or delete the whole `_draft` block).

`metromobile import` refuses the file until you've done that. If
`draft-manifest` says it couldn't extract the plans, fall back to filling
`manifest.template.jsonc` by hand.

## Field reference — what to verify / fill, per plan

Bell's current lineup is mostly **Unlimited-data** plans ("Select" / "Ultra"
tiers with a GB bucket at full speed, e.g. 60 / 100 / 150 GB). Sometimes a
cheaper tiered plan.

### Pricing — one field per tier, kept apart

| field | what it holds | fill it from |
|---|---|---|
| `regular_price_cad` | the **unconditional** price: no bundle, no AutoPay, no promo. The only price the ranking engine uses. | the **struck-through** figure next to the big price — same on both tabs |
| `autopay_price_cad` | price when the **only** condition is AutoPay. Leave **null** if AutoPay's saving is combined with a promo / new-activation credit that Bell doesn't itemise. | a distinct "with automatic payments only $__" figure — rare |
| `promo_price_cad` | the big price on the **Mobility only** tab (AutoPay credit + promotional/new-activation credit, no bundle) | Mobility-only tab big price |
| `promo_conditions` | every condition the promo price needs (AutoPay + new activation + pre-auth debit within 31 days, etc.) | Bell's caption + footnotes |
| `promo_stacks_conditions` | `"requires automatic payments (AutoPay)"` — so a default user still pays regular | (auto) |
| `promo_ends_at` / `promo_expiry_known` | `promo_expiry_known` = **`false`** unless Bell states a real end date; then set the date + `true` | the promo fine print |
| `bundle_price_cad` | the big price on the **With Streaming** tab | With-Streaming tab big price |
| `bundle_conditions` | eligible Crave/Netflix/Disney+ bundle (−$15/mo credit, lost on plan change) **+ AutoPay + promo/new-activation eligibility** | the bundle footnote |
| `pricing_notes` | free-form `[{amount, label}]` the drafter observed — leave as-is for provenance | (auto) |

Rule of thumb: if a price needs *anything* (a bundle, AutoPay, a new activation,
a promo credit), it does **not** go in `regular_price_cad`.

### Restricted / exclusive offers

If a capture shows an **Exclusive Partner Offer**, **Lite** plan, employee plan,
or any invite-only price:

* keep the plan if it's useful,
* set `eligibility_restricted: true` and record the exact condition in
  `eligibility_conditions`,
* the ranking engine then **excludes it from the default Top 5** — it can only
  rank for a user known to meet the condition.

The drafter auto-flags obvious cases ("Exclusive Partner Offer", "employee plan",
etc.); verify and complete the condition text.

### Everything else

| field | where on the page | notes |
|---|---|---|
| `plan_name` | the plan card title | exact text, e.g. `Select - 60 GB` |
| `autopay_required` | `true` if any headline price needs autopay | Bell's usually does |
| `data_full_speed_gb` | "60 GB of data at up to 2 Gbps" | the full-speed bucket |
| `data_total_gb` | **only** for a genuine hard cap (no "unlimited … thereafter") | otherwise `null` |
| `data_unlimited` | `true` — Bell keeps working (throttled) after the bucket | |
| `data_unlimited_is_full_speed` | `false` for Select (slows after the bucket); `true` for a genuinely unlimited full-speed Ultra | |
| `throttle_speed` | e.g. `"512 Kbps"` — "unlimited data at up to 512 Kbps thereafter" | |
| `hotspot_data_gb` | the hotspot bucket, e.g. `50` | this is a **hotspot** cap, not the plan's total data — never copy it into `data_total_gb` |
| `network_technology` / `has_5g` | "5G" / "5G+" badge on the card | |
| `canada_wide_calling` / `unlimited_text` | usually "Unlimited talk & text" | `true` if stated |
| `includes_us` / `includes_mexico` | ONLY if the plan says "Canada/US" or "Canada/US/Mexico" data or calling | most Bell plans are Canada-only → `false` |
| `data_promo_gb` | "Get 20GB bonus for a limited time" style | temporary bonus |
| `activation_fee_cad` | Bell's Connection Fee (~$60) — usually a footnote or checkout only | if not on this page → `null` |
| `available_regions` | leave `null` unless the plan is explicitly BC-only | Bell plans are national |

## 4. Bell pitfalls (easy to misread)

* **The big price is not the plan price.** On the Mobility-only tab it combines an
  AutoPay credit **and** a promo/new-activation credit → `promo_price_cad`, not
  `autopay_price_cad` (AutoPay's share isn't itemised). On the With-Streaming tab
  it adds a $15 bundle credit → `bundle_price_cad`. The **struck-through** figure
  is the unconditional `regular_price_cad`.
* **AutoPay-only price.** Only if the page shows a price whose *sole* condition is
  automatic payments (no promo/new-activation credit mixed in) does it go in
  `autopay_price_cad` + `autopay_conditions`. Bell's current pages don't — set
  `autopay_required: true` and leave `autopay_price_cad` null.
* **Streaming / Internet bundle.** "Save $15/mo when you bundle with Crave /
  Netflix / Disney+ / Bell Internet." → `bundle_price_cad` + `bundle_conditions`.
  Never lower `regular_price_cad` for it.
* **Promo credit inside the price.** "$X/mo for the first 12 months" or "limited
  time" → `promo_price_cad`, `promo_ends_at` / `promo_expiry_known`, and
  `promo_stacks_conditions` if the promo *also* needs AutoPay/bundle.
* **Additional-line pricing / "Average price per line".** "$__/mo on lines 2–4",
  "average price per line for 3 lines". Ignore — single / first-line only. The
  drafter records these in `pricing_notes` for reference; don't promote them.
* **"with a phone" pricing.** If you didn't switch to Bring-your-own-phone, the
  price shown includes a device subsidy/financing line. Re-check the toggle.
* **Unlimited ≠ unlimited full speed.** "60 GB of data … then unlimited data at
  up to 512 Kbps thereafter" → `data_full_speed_gb: 60`, `data_unlimited: true`,
  `data_unlimited_is_full_speed: false`, `throttle_speed: "512 Kbps"`,
  `data_hard_cap: false`, and `data_total_gb: null` (it is **not** a 60 GB cap).
* **Genuinely unlimited Ultra plans.** "Unlimited data at our fastest speeds" →
  `data_unlimited: true`, `data_unlimited_is_full_speed: true`. Do not invent a
  finite `data_total_gb` just because the **hotspot** allowance has a number.
* **Connection Fee.** Bell charges one (~$60–70), but it's usually only shown at
  checkout. If it's not stated on the plans page, leave `activation_fee_cad`
  null — don't guess the amount.
* **5G vs 5G+.** These are different tiers on Bell; copy exactly what the card
  says into `network_technology`.
* **Auto-draft is a starting point, not the truth.** The `_review.confidence` and
  `_review.warnings` are hints. The Bell page you captured is the authority — the
  drafter can misread a bundled price or miss a footnote.

## 5. Import (after you've marked the draft reviewed)

```bash
cd backend
.venv/bin/metromobile import \
  --manifest imports/bell/captures/2026-09-06.plans.jsonc \
  --capture  imports/bell/captures/2026-09-06.mhtml \
  --operator <your-name>
```

`--verified-at` is **optional** — omit it and the import records "verified now"
(the moment you run the command). Pass it only if you're importing a capture you
saved on an earlier day, e.g. `--verified-at 2026-09-01T14:00:00Z`.

A Bell capture stays **current for 7 days**, shows an **aging** warning after
that, and goes **stale + ranking-ineligible after 14 days** — then re-run with
`metromobile reverify` (see `../README.md`). If a promo you captured has a real
expiry date, that offer stops counting the moment it expires, regardless of how
fresh the capture is.
