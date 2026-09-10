# Ranking Engine Design Report

Status: **design only — nothing in this document is implemented.** Written against
the real V1 dataset (33 plans / 26 verified official plans / 24 default-rankable +
2 verified eligibility-gated student plans) across Chatr, Bell, Koodo, Freedom
Mobile, as of 2026-09-09. No code changes accompany this report.

---

## 0. A blocking finding, found while inspecting the data

**Prices are not currently period-normalized, and one rankable plan is annual.**

`Chatr — "$159 Canada-wide Talk & International Text 40GB (12 Months)"` has
`price_period="annual"`, `term_months=12`, `regular_price_cad=159`. That `159` is
the price **for the whole year**, not per month — its true monthly-equivalent cost
is `159 / 12 = $13.25/mo`, which would make it the **cheapest** plan in the entire
catalogue (for 40 GB of data), not the most expensive.

`universal_price_cad` / `regular_price_cad` / `effective_price_cad` in
`pricing.py` today pass this number through unchanged. If "Cheapest" or any
price component sorted on the raw field, this plan would rank as if it cost
$159/mo — a 12x distortion in the wrong direction.

**Required pre-scoring step, before any component formula runs:**

```
monthly_equivalent_price(plan) =
    universal_price_cad / term_months   if price_period == "annual"
    universal_price_cad                  otherwise (monthly, or unspecified)
```

All formulas below assume this normalization has already happened — every
`price` reference is a monthly-equivalent figure. This needs to be added to
`pricing.py` (or a new `ranking.py`) as a real code change before scoring exists;
it is called out here because it changes which plan is "cheapest" today, and it's
the kind of gap that's easy to miss when the field is just called
`regular_price_cad`.

---

## 1. What we actually have — field inventory

Computed against the 27 official plans (24 rankable + 2 verified-but-restricted;
the 1 `provisional` Chatr plan is excluded from ranking already by validation and
isn't counted here).

### Reliable enough to score directly

| field | filled | use |
|---|---:|---|
| `regular_price_cad` / `universal_price_cad` | 27/27 | Price component (after period normalization) |
| `effective_price_cad` | 27/27 | "what a default user pays now" — always equals `universal_price_cad` today (see §7) |
| `data_unlimited`, `data_hard_cap` | 25/27, 24/27 | data-shape classification (finite vs throttle-unlimited vs genuinely-unlimited) |
| `data_full_speed_gb` / `data_total_gb` (fallback chain) | 23/27 direct + resolvable for the rest | Data component |
| `canada_wide_calling`, `unlimited_text` | 26/27, 26/27 | Features component (talk/text) |
| `network_technology`, `has_5g` | 24/27, 24/27 | Network tier |
| `includes_us`, `includes_mexico` | 17/27, 16/27 | Roaming component |
| `is_current_offer`, `price_tiers` | 27/27, 27/27 | Offer component |
| `eligibility_restricted`, `eligibility_conditions` | 2/27 (by design — most plans aren't restricted) | candidate-pool gating |
| `verification_status`, `is_rankable`, `last_verified_at` | 27/27 | candidate pool, tie-breaks |

### Present but too sparse / unreliable to be a primary scoring axis in V1

| field | filled | why it's excluded (or demoted to a bonus) |
|---|---:|---|
| `max_download_mbps` | 9/27 | Too sparse to be primary; used only as a same-tier tiebreak bonus, never the main network score |
| `network_speed_tier` | 5/27 | Free-text marketing string, inconsistent format; not used for scoring |
| `hotspot` / `hotspot_data_gb` | 4/27 / 2/27 | Only Bell states this; used as a small bonus, never a penalty for being null |
| `international_roaming_note` | 10/27 | Used for the *explanation text*, not the number itself (text isn't a score) |
| `contract_required` | 7/27 | Not reliable enough to score; usable only as a hard filter *when explicitly known* |
| `promo_expiry_known` | 15/27 | Used in Offer scoring as an uncertainty multiplier, not a pass/fail |
| `promo_duration_months` | 1/27 | Used as a small bonus when present, zero effect when absent |

### Present in the schema, zero real data — do not score these in V1

| field | filled | notes |
|---|---:|---|
| `esim` | 0/27 | Schema exists, no provider has ever populated it. A hard filter on this would currently exclude every plan. |
| `wifi_calling` | 0/27 | Same. |
| `activation_fee_cad` | 0/27 | Every provider left this null (correctly — none of our captures showed one explicitly). Cannot be scored or filtered. |
| `available_regions` | 0/27 | No plan is marked BC-only; not usable for location logic (see §11). |
| `student_offer` | 1/27 (only the Freedom variant) | Koozo's Student deal doesn't set this flag even though it's a student plan — a labeling gap in the Koodo importer worth fixing later, noted here rather than silently worked around. |

**Implication:** any customization filter or scoring axis built on the "zero real
data" fields must be visibly disabled or clearly labeled "not yet verified for any
plan" rather than silently returning an empty result set (see §12).

---

## 2. Candidate pool rules

A plan enters the **default** candidate pool for all five presets if and only if:

```
is_rankable == True
```

This already encodes: verified (not provisional/stale/secondary-unconfirmed),
fresh within its source mode's window, has a known unconditional price, has a
known data signal, and — the one this report adds meaning to — **is not
`eligibility_restricted`**.

A plan with `eligibility_restricted == True` enters the pool **only** when the
matching **eligibility flag** is confirmed by the user (see §8) — never by default,
never because a preset happens to be named "Students."

---

## 3. Price normalization detail (feeds every component)

```
price(plan) = monthly_equivalent_price(plan)          # §0
```

For **Best Overall / Cheapest / Most Data / Best for Students** (default, no
eligibility confirmed): `price = universal_price_cad` (the unconditional
"regular" price) — **never** `promo_price_cad`, `bundle_price_cad`, or
`autopay_price_cad`. This is the direct implementation of "conditional prices
must not silently make a plan appear cheaper for a user who may not qualify."

For **Best Current Offers**: the *display* price is still `universal_price_cad`,
but the *offer value* (§6) is computed from the gap between `universal_price_cad`
and the best available conditional tier, with the condition's burden priced in —
so a cheap-looking conditional tier doesn't quietly become "the price."

When a user has confirmed an eligibility flag (autopay-willing, student-eligible,
etc. — §8), `price(plan)` swaps to the matching tier **for that plan only**, and
the swap is always visible in the explanation ("using your AutoPay price of
$X because you confirmed AutoPay").

---

## 4. Data normalization detail (feeds the Data component)

```
data_gb(plan):
    if data_unlimited_is_full_speed == True:
        return UNLIMITED                     # genuinely unlimited at full speed
    if data_full_speed_gb is not None:
        return data_full_speed_gb            # full-speed bucket, whether or not
                                              # it throttles afterward
    if data_total_gb is not None:
        return data_total_gb                 # a stated hard-cap total
    if data_unlimited == False and no numeric field is set:
        return 0.0                           # KNOWN to include no data
                                              # (e.g. Koodo Pay-per-use)
    return UNKNOWN                            # true gap — see §9
```

This value is used **only** for the plan's own domestic full-speed allowance.
Per your explicit instruction, it **never** includes:
- Roam Beyond / international roaming GB (`attributes.roam_beyond_data_gb`)
- hotspot GB (`hotspot_data_gb`)
- any other provider's bonus/promo GB that isn't part of the base allowance

`UNLIMITED` sorts and scores as the maximum (100), ahead of every finite number,
never as a fabricated large number like "999999".

---

## 5. Component scores — formulas

Six raw components, each 0–100, computed identically regardless of preset (only
the *weights* differ per preset). Two of them (Network, Roaming) fold into the
single "Network/Location" and "Features" lines you described; the mapping is in
§5.8.

### 5.1 Price score (P)

```
PRICE_FLOOR = 10      # $/mo, calibration constant, below the cheapest plan seen
PRICE_CEIL  = 120     # $/mo, calibration constant, above the priciest plan seen

P = 100 * clamp((PRICE_CEIL - price) / (PRICE_CEIL - PRICE_FLOOR), 0, 1)
```

Linear, not log — the observed price range ($13–$110/mo once period-normalized)
is less than 10x, so linear stays easy to explain ("cheapest end of our observed
range scores near 100, priciest scores near 0") without log-scale's extra
justification burden. These two constants are the only tunable numbers in this
formula and should be revisited if the catalogue's price range shifts a lot
(e.g. if a $200/mo enterprise plan is ever added).

### 5.2 Data score (D)

```
DATA_CAP = 150   # GB, calibration constant — see rationale below

D = 100                                             if data_gb(plan) is UNLIMITED
D = 0                                                if data_gb(plan) == 0
D = 100 * min(1, ln(1 + gb) / ln(1 + DATA_CAP))      otherwise
```

Log, not linear — GB in our data spans 0.25 to 250+ (three orders of magnitude).
A linear scale would make a 250 GB plan look ~1000x "better" than a 250 MB plan,
which doesn't reflect real usage value (a typical user gets most of the value
from the first ~50–100 GB; a 250 GB plan is not meaningfully "more useful" than a
150 GB plan for the overwhelming majority of users). The log curve captures that
diminishing return honestly; `DATA_CAP=150` is the point past which the score
is within a couple of points of maxing out at 100.

### 5.3 Network score (N)

```
TECH_TIER = {"5G+": 100, "5G": 85, "4G LTE": 60, "4G": 60, "3G": 30}

N = TECH_TIER[network_technology]     if network_technology is known
N = <renormalize — see §9>            if unknown
```

`max_download_mbps` is **not** part of this formula (too sparse — 9/27). It is
surfaced only as extra explanatory text when present ("up to 2000 Mbps"), never
as points.

### 5.4 Location multiplier (L) — currently neutral

```
L = 1.0   for Vancouver, Burnaby, and Surrey (all three, identically)
```

Full justification in §11. `Network/Location` (the line in your example
breakdown) = `N × L`. Since `L = 1.0` everywhere today, `Network/Location`
currently equals `N` exactly — the multiplier exists in the formula so that
plugging in real per-municipality data later is a one-line change, not a
redesign.

### 5.5 Features score (F) — a small weighted composite, not one field

```
F_talk  = 100 if canada_wide_calling == True else 40 if == False else <renorm>
F_text  = 100 if unlimited_text == True      else 40 if == False else <renorm>
F_hot   = 100 if hotspot == True             else 50  (neutral — see §9)

F = 0.55 * F_talk + 0.30 * F_text + 0.15 * F_hot
```

`esim` and `wifi_calling` are **not** in this formula (§1 — zero real data).

### 5.6 Roaming score (Rm)

```
Rm = 100   if includes_us and includes_mexico
Rm = 75    if includes_us only (no includes_mexico)
Rm = 80    if international_roaming == True and neither includes_us nor includes_mexico
Rm = 0     if none of the above are true
```

Capped at 100 even when a plan has *both* full Canada-US-Mexico *and* a separate
Roam Beyond-style global allowance (Freedom) — we don't have a documented,
official per-country value scale to justify scoring past 100, so the extra
coverage is described in the explanation text but doesn't inflate the number.
That's a deliberate conservative choice, flagged here as a candidate refinement
if you want Freedom's broader roaming to count for more later.

Note this formula has **no separate "unknown" branch** — `None` on
`includes_us`/`includes_mexico`/`international_roaming` scores as `0`
(no missing-value renormalization here), unlike Network or Features. That's a
deliberate reading of how these fields are populated: every drafter in this
project is instructed to set `includes_us`/`includes_mexico` **only** when the
official source explicitly states it, and to leave it `null` otherwise —
including when a plan's own text plainly doesn't mention US/Mexico access at
all. In practice, `null` here means "confirmed not advertised," not "we forgot
to check," so scoring it as `0` is a known-fact reading, not a guess. If that
capture discipline ever changes, this section needs to be revisited.

### 5.7 Offer score (O)

Covered in full in §6 (it's the most involved formula and Best Current Offers'
entire reason for existing).

### 5.8 Mapping to your 5-line breakdown

| your line | = |
|---|---|
| Price/value | `P` |
| Data | `D` |
| Network/Location | `N × L` |
| Features | `0.7 * F + 0.3 * Rm` (talk/text/hotspot blended with roaming into one displayed line) |
| Offer value | `O` |

Each of these 5 numbers is independently inspectable (so "Features: 75" can be
expanded on demand into its own `F_talk / F_text / F_hot / Rm` sub-breakdown) —
nothing is a single opaque field.

---

## 6. Best Current Offers — the Offer score in full

This is the component you specifically asked to be fair about: *"A giant discount
requiring an expensive unrelated bundle should not automatically dominate."*

For each plan, look at **every** conditional tier in `price_tiers` (autopay,
bundle, promo — whichever the plan has), and score each one:

```
discount_pct(tier)   = (universal_price_cad - tier.amount) / universal_price_cad

condition_ease(tier) =
    0.90   if the ONLY condition is AutoPay / pre-authorized payment
    0.70   if AutoPay is mixed with an unspecified/un-itemized promo
           (Bell's "AutoPay + promotional credit" tier, Koodo's mixed tier)
    0.40   if it requires an unrelated bundle (home Internet / streaming)
    0.50   if it requires verified STUDENT eligibility
           (only relevant once student_eligible=true unlocks the tier at all)

expiry_ease(tier) =
    1.00   ongoing / not time-limited (e.g. a standing AutoPay discount)
    1.00   time-limited WITH a stated end date (fully disclosed, no penalty
           for merely being time-limited)
    0.85   time-limited with NO stated end date (promo_expiry_known == False —
           this is the one case that gets penalized: genuine uncertainty)

duration_bonus(tier) = min(10, (promo_duration_months or 0) / 3)

tier_value = 100 * discount_pct(tier) * condition_ease(tier) * expiry_ease(tier)
             + duration_bonus(tier)

O = max(tier_value across all tiers, 0)      # 0 if the plan has no conditional tier at all
```

**Why "pick the best tier" instead of always the cheapest tier:** this is what
prevents a bundle-gated 33%-off deal from automatically crushing a no-strings
9%-off AutoPay deal — the condition penalty is applied *per tier*, so the
formula naturally compresses the gap between "easy, small discount" and "hard,
large discount" rather than just picking whichever price is lowest. §15.4 works
this out with real Bell/Koodo/Freedom numbers and the compression is visible
there.

A plan with zero conditional tiers (many Chatr plans) scores `O = 0` — accurate
("there is currently no disclosed discount on this plan"), not penalized further
elsewhere, and it still appears in the Best Current Offers list ranked
appropriately low, rather than being hidden.

---

## 7. A finding worth flagging on its own: there are no unconditional discounts today

Across all 27 official plans, `effective_price_cad == universal_price_cad` for
**every single one**. Every discount currently on record (Bell's bundle/promo,
Koodo's mixed AutoPay/promo, Freedom's Digital Discount) requires a condition —
so `pricing.py`'s existing "does an active promo beat the regular price for a
default user" check (`is_offer and not offer_conditional`) is correctly returning
"no" for all of them right now.

This isn't a bug — it's just the honest current state of the catalogue, and it's
exactly why Best Current Offers needs the tier-aware formula in §6 rather than a
simple "is there an active unconditional promo" flag: today that flag would make
the entire preset return nothing. It's worth knowing before you look at the first
real Best Current Offers output and wonder why nothing looks like a "% off"
banner in the traditional sense.

---

## 8. Eligibility / conditional-price handling

Two independent boolean flags, both **default false**, both must be explicitly
set by the user — never inferred from which preset they picked:

- `autopay_willing: bool`
- `student_eligible: bool`

(Two more of the same shape are implied by your customization list — `bundle_available` and a general `promo_code_available` — but no plan in the current dataset has a *pure* bundle-only or promo-only tier that isn't already covered by AutoPay/mixed, so they're named here for completeness but have nothing to attach to yet.)

**Effect of `student_eligible = true`:**
1. Candidate pool gains any plan where `eligibility_restricted == True and student_offer == True` (today: the Freedom Post-Secondary variant; Koodo's Student deal should also carry `student_offer=True` once that importer gap — §1 — is closed, otherwise it needs a second signal to be included, e.g. `eligibility_conditions` text-matching "student", which is a weaker, provider-format-dependent check I'd rather avoid relying on long-term).
2. For those plans, `price(plan)` in every formula becomes their `promo_price_cad` (the verified student price), not `regular_price_cad`.
3. Everywhere else, nothing changes — a non-restricted plan doesn't get cheaper just because the user is a student.

**Effect of `autopay_willing = true`:** for any plan whose *only* conditional tier
is AutoPay (`autopay_price_cad` set, no bundle/mixed-promo tier cheaper), `price(plan)`
swaps to `autopay_price_cad` for that plan. Mixed tiers (Bell/Koodo's
AutoPay+promo) are **not** swapped by this flag alone — those need the "I also
have this bundle" / "I understand this includes a promo I might not always have"
level of confirmation, which isn't in the V1 customization list, so those tiers
stay conditional-only and are surfaced strictly through Best Current Offers
(§6), never quietly through Best Overall/Cheapest.

**`eligibility_restricted` plans that don't match any confirmed flag never enter
any candidate pool, under any preset, including Best Current Offers** — a
restricted plan's discount is not "a good current offer for the general public,"
it's a good offer for whoever meets the restriction, and the whole point of the
flag is that we don't know that about the current visitor by default.

---

## 9. Missing-value handling — the explicit rules

Three distinct, separately-justified policies, applied per field, never applied
by accident:

| policy | when used | mechanics |
|---|---|---|
| **Renormalize (exclude + redistribute weight)** | `network_technology` unknown (3/27 plans); `canada_wide_calling`/`unlimited_text` unknown (rare, 1/27 each) | That component is dropped from the weighted sum for *that plan only*, and its weight is redistributed proportionally across the plan's other known components. The plan is scored on what we've verified, nothing is guessed. |
| **Explicit neutral value** | `hotspot` unknown/false (23/27) | Scored as `50` (the midpoint), not `0` and not `100` — because "not stated" is genuinely different from "confirmed absent," and a nice-to-have feature shouldn't swing many plans on a coin-flip either way. This is the one case where a literal neutral number is injected, and it's disclosed as such in the explanation ("hotspot not confirmed for this plan — scored neutrally"). |
| **Known zero (not missing at all)** | `data_gb` when `data_unlimited == False` and no numeric field is set (Koodo Pay-per-use) | This isn't a missing-value case — the source plan genuinely includes no monthly data allowance. Scored `0`, correctly, same as any other verified fact. |

Two components (`Price`, `Data`) essentially never hit a missing-value case among
`is_rankable` plans, because `validation.py` already requires both an
unconditional price and *some* data signal before a plan can be ranked at all —
so the missing-value machinery above only matters for `Network` and `Features`.
`Roaming` (§5.6) deliberately has no missing-value case at all — see the note
at the end of §5.6 for why `null` is read as a known fact there, not a gap.

---

## 10. Tie-breaking

Applied only after rounding the weighted total to 2 decimal places (so floating
noise never manufactures a fake distinction):

1. The preset's own **second-highest-weighted** component, descending (e.g. for
   Cheapest, break ties by Data descending; for Most Data, break ties by Price
   ascending).
2. `last_verified_at`, most recent first (prefer the more recently confirmed
   record when everything else is equal).
3. `is_current_offer == True` before `False` (prefer showing a plan with an
   active disclosed deal, all else equal).
4. `external_id`, lexicographic — guarantees a fully deterministic order with no
   remaining ties, ever.

---

## 11. Location component — Vancouver / Burnaby / Surrey

**What we have:** a `municipality` string passed to the API, a `meta.municipality_affects_results` flag (currently `False`), and a `Plan.available_regions` field that is **0/27 populated** — no plan in our verified dataset states a BC-only, Vancouver-only, or any sub-national restriction. All four providers are national or BC-home-network carriers; their stated coverage claims are provincial/network-tier ("Freedom Network" vs "partner network"), not per-municipality.

**What's missing:** any independently-sourced, per-municipality signal about coverage quality, tower density, or measured speed for Vancouver vs. Burnaby vs. Surrey specifically. Nothing in the codebase fetches or normalizes this today (there's an old architectural placeholder for a `coverage_observations` table from early planning, but it was never built or populated).

**What we'd need, to do this honestly:** a legitimate public dataset — e.g. ISED's spectrum-licensing / National Broadband Data, or CRTC's wireless coverage/quality reporting — mapped to each of the three municipalities and to each of our four providers' networks (or their underlying network owner: Rogers for Chatr, Bell for Bell, TELUS for Koodo, Videotron/Freedom for Freedom), captured the same way every other official source is (fetch → provenance → normalize), with a confidence and a citation.

**How it plugs in later:** exactly through the `L` multiplier already in the formula (§5.4) — `Network/Location = N × L(provider, municipality)`. The day real coverage data exists, `L` stops being a flat `1.0` and becomes a per-(provider, municipality) lookup, and nothing else about the scoring pipeline changes.

**Recommendation for V1:** keep `L = 1.0` everywhere and keep `municipality_affects_results = false`, matching what the flag already (correctly) says. Vancouver, Burnaby, and Surrey will show **identical** rankings until real coverage data exists — that's a plain, honest gap, not a bug to paper over with invented small differences between the three.

---

## 12. Customization architecture — hard filters vs. soft preferences vs. eligibility flags

Three distinct mechanisms, because they behave differently and conflating them
causes exactly the kind of silent unfairness this whole design is trying to avoid:

### Hard filters (exclude the plan entirely)

| filter | mechanics | caveat |
|---|---|---|
| Maximum monthly budget | `price(plan) <= budget` | uses the unconditional price unless an eligibility flag applies (§8) |
| Minimum full-speed data | `data_gb(plan) >= threshold` (UNLIMITED always passes) | — |
| Prepaid / postpaid | `plan_type == choice` | `plan_type` is always known for rankable plans |
| Canada-US-Mexico required | `includes_us and includes_mexico` | if the user says they need this, "unknown" must be treated as **not met** — we can't claim a plan satisfies a hard requirement we haven't verified |
| eSIM required | `esim == True` | **currently would exclude every plan (0/27 populated)** — must ship disabled with a visible "not yet verified for any plan" message, not silently return zero results |
| Hotspot required | `hotspot == True` | Only 4/27 plans confirm this either way. Recommend showing a disclaimer alongside this filter ("only plans with *confirmed* hotspot support are shown; others may also support it but it isn't stated in our verified data") rather than implying the filtered list is complete |

### Eligibility-confirmation flags (swap which price/tier applies, then score normally — §8)

- `student_eligible`
- `autopay_willing`

### Soft preferences (re-weight, never exclude)

| preference | mechanics |
|---|---|
| Value/cheapness slider | shifts a portion of weight from Data/Network/Features into Price, linearly, then renormalizes the weight vector to sum to 100% |
| 5G preference | multiplies `N` by a small bonus (e.g. ×1.1, capped at 100) when `has_5g == True`, rather than changing the tier map itself |
| International roaming importance | increases the sub-weight of `Rm` inside the Features blend (§5.8) for that user's session |
| "I want a good deal" (promotion preference) | increases the preset's own Offer weight, same mechanic Best Current Offers uses natively, just dialed up on any preset |

Pipeline, end to end:

```
1. candidate pool  = is_rankable plans
                    + eligibility-unlocked restricted plans (if flags set)
2. apply hard filters (budget, data floor, plan type, CA-US-MX, eSIM, hotspot)
3. resolve price(plan) per plan using confirmed eligibility flags
4. compute the 6 raw component scores (same formulas, always)
5. take the preset's base weight vector, apply soft-preference adjustments,
   renormalize to 100%
6. weighted sum -> Overall score, rounded to 2 decimals
7. tie-break chain (§10)
8. (optional, see §14) soft diversity adjustment at Top-5 selection only
9. return Top 5 + full component breakdown, citing which fields were
   renormalized/neutral-filled/known-zero for that specific plan
```

---

## 13. Proposed weights per preset

All five presets share the same six components and the same formulas — only the
weight vector changes. Cheapest and Most Data are the same engine at an extreme
weight vector plus their tie-break chain, not a separate code path.

| preset | Price | Data | Network/Loc | Features | Offer |
|---|---:|---:|---:|---:|---:|
| **Best Overall** | 30% | 25% | 20% | 15% | 10% |
| **Cheapest** | 100% | 0% | 0% | 0% | 0% (tie-break: Data desc, then §10) |
| **Most Data** | 0% | 100% | 0% | 0% | 0% (tie-break: Price asc, then §10) |
| **Best Current Offers** | 25% | 15% | 5% | 5% | 50% |
| **Best for Students** | 40% | 25% | 10% | 10% | 15% |

**Best for Students isn't just Cheapest with a different label** — Price is
weighted higher than Best Overall (40% vs 30%) because cost genuinely dominates
student decision-making, but Data stays substantial (25%, same as Best Overall)
because a plan that's cheap but useless for coursework/streaming isn't a good
student plan either, and Offer is boosted (15% vs 10%) because this is the one
preset where a `student_eligible=true` flag can unlock genuinely lower verified
prices (§8) — so rewarding good offers here has real teeth, unlike a slider that
only ever discounts prices nobody currently qualifies for.

---

## 14. Provider diversity

**The concern:** Top 5 is plan-level, and today Koodo alone has 8 rankable plans
across a wide price range — a pure score ranking could plausibly fill 3-4 of 5
Top-5 slots with Koodo plans for some presets, which is technically correct but
can read as favoritism and isn't very useful for someone trying to compare
carriers.

### Option A — pure score ranking, no diversity logic
- **Pros:** simplest, fully auditable (`the Top 5 is exactly the 5 highest scores, full stop`), no invented constants.
- **Cons:** can produce a Top 5 that looks monotonous or carrier-biased even when it's mathematically correct, which can undermine trust in a way that's hard to explain away with "the math said so."

### Option B — hard cap (e.g. max 2 plans per provider in the Top 5)
- **Pros:** guarantees carrier variety, matches a shopper's mental model of "show me the market," simple to state.
- **Cons:** can force a genuinely worse plan (by every stated metric) ahead of a better one from an already-represented provider — which contradicts "deterministic and auditable" in spirit even though the *rule* is deterministic. Also needs an arbitrary cap number (2? 3?) with no principled derivation.

### Option C — soft diversity penalty at Top-5 selection only
- **Mechanics:** the underlying score (what's displayed as "Overall 87") stays pure and untouched. Only the *selection* step applies a decreasing multiplier to a provider's 2nd, 3rd, ... pick when assembling the final Top 5 (e.g. 1st pick from a provider: full score; 2nd pick: score × 0.92; 3rd+: score × 0.85), then re-sorts for selection.
- **Pros:** self-limiting — a small penalty can't demote a plan that's overwhelmingly better than the alternatives; it only matters when plans are already close. The *displayed* score for every plan stays the true, unadjusted number, so nothing about the auditability principle is compromised — the diversity nudge is a disclosed, separate selection step, not a scoring change.
- **Cons:** two more tunable constants (0.92, 0.85) that need justification/tuning, and it's one more mechanism to explain (though it's genuinely simple to explain: "your 2nd-best pick from a provider you've already shown once gets a small nudge down").

**Recommendation:** don't ship any diversity logic in the first ranking release.
Ship pure score ranking (Option A), actually look at what the real Top 5s look
like across the five presets and three municipalities once weights are tuned,
and only add Option C — the soft penalty, never the hard cap — if real output
shows a provider dominating in a way that looks bad in practice. Inventing a
diversity correction before observing whether the problem actually occurs risks
solving a problem that doesn't exist yet, and (per your own principle) adds a
component to the algorithm we can't yet justify with real evidence. This is
consistent with how every other part of this design treats evidence.

---

## 15. Worked examples (real plans, real numbers)

Calibration constants used throughout: `PRICE_FLOOR=10, PRICE_CEIL=120, DATA_CAP=150`.

### 15.1 Best Overall — three similarly-priced mid-tier plans

| | Bell Select 60GB | Koodo 60GB (5G) | Freedom 70GB+Roam1GB |
|---|---:|---:|---:|
| price (monthly-equiv, unconditional) | $75 | $60 | $45 |
| data_gb | 60 | 60 | 70 |
| network_technology | 5G+ | 5G | 5G+ |
| canada_wide_calling / unlimited_text | True / True | True / True | True / True |
| hotspot | True | unknown | unknown |
| includes_us / includes_mexico | None / None | None / None | True / True |

Component scores:

- **P**: Bell `100*(120-75)/110=40.9`; Koodo `100*(120-60)/110=54.5`; Freedom `100*(120-45)/110=68.2`
- **D**: Bell `100*ln(61)/ln(151)=81.9`; Koodo `81.9` (same GB); Freedom `100*ln(71)/ln(151)=84.9`
- **N**: Bell `100` (5G+); Koodo `85` (5G); Freedom `100` (5G+)
- **F**: Bell `0.55*100+0.30*100+0.15*100=100`; Koodo `0.55*100+0.30*100+0.15*50=92.5` (hotspot unknown → neutral 50); Freedom `92.5` (same, hotspot unknown)
- **Rm**: Bell `0` (no US/Mexico); Koodo `0`; Freedom `100` (US+Mexico)
- **Features line** (`0.7F + 0.3Rm`): Bell `0.7*100=70.0`; Koodo `0.7*92.5=64.75`; Freedom `0.7*92.5+0.3*100=94.75`

Best Overall = `0.30P + 0.25D + 0.20N + 0.15Features + 0.10O`, where `O` is each
plan's own best conditional-tier offer score (§6), computed from its real
`price_tiers`:

- **Bell Select 60GB** — best tier: bundle @ $50 (reg $75). `discount=0.333`,
  `condition_ease=0.40` (bundle), `expiry_ease=1.00` (this bundle tier's own
  conditions text has no "limited time" language). `O = 100*0.333*0.40*1.00 = 13.3`
- **Koodo 60GB** — best (only) tier: promo @ $50 (reg $60). `discount=0.167`,
  `condition_ease=0.70` (mixed AutoPay+un-itemized promo), `expiry_ease=0.85`
  ("limited time, no end date published"). `O = 100*0.167*0.70*0.85 = 9.9`
- **Freedom 70GB** — best (only) tier: AutoPay @ $40 (reg $45). `discount=0.111`,
  `condition_ease=0.90` (AutoPay only), `expiry_ease=1.00` (ongoing, no
  time-limit language). `O = 100*0.111*0.90*1.00 = 10.0`

| | Bell | Koodo | Freedom |
|---|---:|---:|---:|
| Overall | `.30(40.9)+.25(81.9)+.20(100)+.15(70.0)+.10(13.3)` = `12.27+20.48+20.0+10.5+1.33` = **64.6** | `.30(54.5)+.25(81.9)+.20(85)+.15(64.75)+.10(9.9)` = `16.35+20.48+17.0+9.71+0.99` = **64.5** | `.30(68.2)+.25(84.9)+.20(100)+.15(94.75)+.10(10.0)` = `20.46+21.23+20.0+14.21+1.0` = **76.9** |

**Result: Freedom 70GB (76.9) > Bell Select 60GB (64.6) > Koodo 60GB (64.5).**
Freedom wins mainly on price and the Canada-US-Mexico roaming bonus; Bell and
Koodo land in a near-tie (0.1 points apart) — Bell's higher network/feature
scores almost exactly offset its higher price against Koodo's cheaper,
slightly-lower-tier plan. That near-tie is a good sign the weights aren't
accidentally making one component dominate the others.

### 15.2 Cheapest — the annual-plan catch, worked

Naively sorting by raw `regular_price_cad` ascending among Chatr's plans would
put the $159/yr plan **last** (looks like $159/mo). After the §0 normalization:

| plan | raw price | period | monthly-equivalent | data |
|---|---:|---|---:|---:|
| Chatr $19 Talk & Intl Text | $19 | monthly | **$19.00** | 0.5 GB |
| Chatr $159 (12 Months) 40GB | $159 | annual, 12 mo | **$13.25** | 40 GB |

Cheapest mode, correctly normalized: **the $159/year plan ranks #1 at $13.25/mo**
— for 40 GB, not 0.5 GB. This is the single most important behavior for
"Cheapest" to get right, and it only works if the period normalization in §0 is
implemented before scoring, not treated as a nice-to-have.

Zooming out to all 24 rankable plans, Cheapest mode (pure price sort, tie-break
by Data descending) produces, top of the list:

1. Chatr 40GB (12mo) — $13.25/mo
2. Koodo 250MB — $15.00/mo
3. Chatr $19 — $19.00/mo
4. Chatr $21 (1GB) — $21.00/mo
5. Chatr $25 (5GB) — $25.00/mo

This is exactly why the report earlier warned about "don't call a plan best
simply because it's cheapest without distinguishing what Cheapest means" —
#2 (250 MB) is objectively the 2nd-cheapest plan, and it will show as such,
honestly. The recommended mitigation is a **UI-level** one, not an algorithm
change: always display the data allowance next to the price in a Cheapest list,
so "$15/mo, 250 MB" reads as a fact, not a false promise of "best plan."
(explicitly noted as a UI follow-up, not something to silently filter here).

### 15.3 Most Data — genuinely-unlimited vs. large finite

| plan | data_gb | D score |
|---|---:|---:|
| Bell Ultra (US/Mexico roaming) | UNLIMITED (`data_unlimited_is_full_speed=True`) | **100** |
| Bell Ultra (international roaming) | UNLIMITED | **100** |
| Freedom 250GB+Roam Beyond 20GB | 250 | `100*ln(251)/ln(151) = 110.1 -> clamped to 100` |
| Freedom 175GB+Roam Beyond 10GB | 175 | `100*ln(176)/ln(151) = 103.0 -> clamped to 100` |
| Koodo 100GB | 100 | `100*ln(101)/ln(151) = 91.9` |

Most Data mode = pure Data sort. The two Bell Ultra plans and three of the large
Freedom plans **tie at the score cap** (100) — this is intentional (§5.2: past
~150GB we don't claim to distinguish "more useful"), so the **tie-break**
(§10: Price ascending) decides the actual order among the tied group:

1. Freedom 175GB+Roam Beyond 10GB — $55/mo (cheapest among the tied 100s)
2. Freedom 250GB+Roam Beyond 10GB — $65/mo
3. Freedom 250GB+Roam Beyond 20GB — $75/mo
4. Bell Ultra (US/Mexico roaming) — $95/mo
5. Bell Ultra (international roaming) — $110/mo
6. Koodo 100GB — $70/mo, `D=91.9` — the first plan **not** tied at the cap,
   correctly placed below all five even though it's cheaper than three of them,
   because 100 GB genuinely scores below the ~150 GB+ tier on this axis

This demonstrates the hard-cap/throttled-unlimited/genuinely-unlimited
distinction working correctly: Bell's genuinely-unlimited plans and Freedom's
large-but-finite plans compete on equal footing once both exceed the point of
diminishing returns, and price breaks the tie rather than an arbitrary "GB always
wins" rule that would otherwise let 250 GB beat "unlimited" on a technicality.

### 15.4 Best Current Offers — the "expensive bundle shouldn't dominate" case

Already computed in full in §6; summarized here as the worked example:

| plan | best tier | discount % | condition | condition_ease | expiry_ease | O |
|---|---|---:|---|---:|---:|---:|
| Bell Select 60GB | bundle @ $50 (reg $75) | 33.3% | streaming bundle + AutoPay (no promo language in this tier) | 0.40 | 1.00 | **13.3** |
| Koodo 20GB | promo @ $45 (reg $55) | 18.2% | AutoPay + un-itemized promo | 0.70 | 0.85 | **10.8** |
| Freedom 175GB | AutoPay @ $50 (reg $55) | 9.1% | AutoPay only | 0.90 | 1.00 | **8.2** |

Bell's raw discount (33.3%) is **3.7x** Freedom's (9.1%), but after the condition
and expiry multipliers, Bell's *offer score* (13.3) is only **~1.6x** Freedom's
(8.2) — the bundle requirement measurably compresses its advantage instead of
letting the largest raw discount automatically dominate the ranking, which is
exactly the behavior you asked for.

### 15.5 Best for Students — the two-state toggle, worked

**State: `student_eligible = false` (default).** The Koodo Student deal and
Freedom Post-Secondary variant are not in the candidate pool at all — they don't
appear, aren't scored, aren't "almost shown." The Students preset ranks the same
24 plans as everyone else, just with the Students weight vector (§13):

- Freedom 70GB: `.40(68.2)+.25(84.9)+.10(100)+.10(94.75)+.15(10.0)` = `27.28+21.23+10.0+9.48+1.5` = **69.5**
- Koodo 20GB (5G): price=$55, `P=100*(120-55)/110=59.1`; `D=100*ln(21)/ln(151)=60.7`; `N=85` (5G); hotspot unknown (neutral 50) and `Rm=0` (no US/Mexico) gives `Features=0.7*92.5+0.3*0=64.75`; `O=10.8` (§15.4). `.40(59.1)+.25(60.7)+.10(85)+.10(64.75)+.15(10.8)` = `23.64+15.18+8.5+6.48+1.62` = **55.4**

Freedom's data-per-dollar and roaming bonus keep it ahead even under the
Students weighting.

**State: `student_eligible = true`.** The Koodo Student deal (10GB, `$50`
regular / `$40` verified student price) and the Freedom variant (175GB, `$55`
regular / `$45` verified student price) enter the pool, and their `price(plan)`
becomes the student price:

- Koodo Student 10GB: `P = 100*(120-40)/110 = 72.7`, `D = 100*ln(11)/ln(151) = 47.8`, `N=85 (5G)`, `Features≈0.7*92.5=64.75`(no Rm), `O`: its own conditional tier collapses once we're already using the eligibility-unlocked price as the baseline for this flag-state, so `O=0` here to avoid double-crediting the same discount as both "the price we're using" and "an offer bonus". Overall = `.40(72.7)+.25(47.8)+.10(85)+.10(64.75)+.15(0)` = `29.08+11.95+8.5+6.48+0` = **56.0**
- Freedom Student 175GB: `P = 100*(120-45)/110=68.2`, `D=100 (175GB, capped)`, `N=100`, `Features=94.75` (has Rm=100), `O=0` (same reasoning). Overall = `.40(68.2)+.25(100)+.10(100)+.10(94.75)+.15(0)` = `27.28+25.0+10.0+9.48+0` = **71.8**

Freedom's student variant (71.8) beats its own regular-pool showing under
Students weighting in the false-state (69.5) — correctly, since a qualifying
student really does get more value (more data, same price bracket, at a genuine
$10 discount) than a non-student browsing the same catalogue. The Koodo student
plan (56.0) trails because 10GB is a real constraint even at a good price — the
Data component is doing its job of not letting "cheap" alone win a preset that
isn't Cheapest.

---

## 16. Open items to confirm before implementation

1. **Confirm the calibration constants** (`PRICE_FLOOR=10, PRICE_CEIL=120,
   DATA_CAP=150`) — reasonable against today's data, but worth agreeing on
   explicitly since they're the only "made up" numbers besides the offer-condition
   multipliers, and they should live in `config.py` as named, documented
   settings, not magic numbers in the scoring code.
2. **Confirm the offer condition-ease multipliers** (0.90 / 0.70 / 0.40 / 0.50) —
   these encode a judgment call about how burdensome each condition type is;
   they're internally consistent but there's no dataset to derive them from
   empirically, so they should be treated as an initial, adjustable policy.
3. **Decide on the Koodo `student_offer` flag gap** (§1, §8) — either fix the
   Koodo importer to set it, or define a fallback matching rule for Students-mode
   eligibility unlocking.
4. **Confirm the diversity recommendation** (§14: ship without it, revisit with
   real output) before the first Top-5 release.
5. **period-normalization (§0) is a required code change**, not optional
   polish — it changes today's actual Cheapest ordering.

Nothing above requires new provider ingestion or a UI change. Stopping here per
your instruction — ready to review the formulas together before any of this
becomes code.
