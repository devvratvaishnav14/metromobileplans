"""Pricing-tier + current-offer resolution.

A carrier's headline number often bundles several conditional discounts
(AutoPay, a home-internet / streaming bundle, a time-limited promo). Each tier is
stored separately; this module decides, for a given moment:

* ``universal_price_cad`` -- the UNCONDITIONAL price a default user pays
  (no AutoPay, no bundle, no promo). This is what a neutral ranking must use.
* ``best_case_price_cad`` -- the lowest achievable price if every condition is met
  and the promo is active.
* ``tiers`` -- every priced tier with its conditions, cheapest-eligible first.
* offer state -- whether a promo is a *current* offer (an expired promo never is,
  and its price never counts).

Nothing is guessed: a tier only exists if the source stated its price.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


def _num(v) -> float | None:
    return float(v) if v is not None else None


def _dt(v) -> dt.datetime | None:
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    if v.tzinfo is None:
        v = v.replace(tzinfo=dt.timezone.utc)
    return v


@dataclass
class PriceView:
    universal_price_cad: float | None      # unconditional (regular) price
    display_price_cad: float | None        # what to show by default (universal, else most conservative known)
    best_case_price_cad: float | None      # lowest price with all conditions met + active promo
    tiers: list[dict] = field(default_factory=list)
    has_conditional_discounts: bool = False
    price_note: str | None = None          # e.g. "$50/mo requires Bell Internet + AutoPay"

    # --- period normalization (ranking must use this, never the raw amount) ---
    # universal_price_cad / regular_price_cad is preserved untouched above; this is
    # ONLY the derived monthly-equivalent used by scoring. e.g. Chatr's $159/12mo
    # plan -> monthly_equivalent_price_cad=13.25, while universal_price_cad stays 159.
    monthly_equivalent_price_cad: float | None = None
    billing_period: str | None = None       # "monthly" | "annual" | None, passed through
    term_months: int | None = None          # passed through
    upfront_price_cad: float | None = None  # the amount actually billed per invoice (annual: full year)

    # --- offer state -----------------------------------------------
    has_promo: bool = False
    offer_active: bool = False
    offer_expired: bool = False
    expiry_known: bool | None = None
    is_current_offer: bool = False          # active promo beating the universal price
    offer_is_conditional: bool = False      # the promo also needs autopay/bundle
    savings_cad: float | None = None
    offer_note: str | None = None
    effective_price_cad: float | None = None  # serve-time "what a default user pays now"


def price_view(plan, now: dt.datetime) -> PriceView:
    g = lambda k: getattr(plan, k, None)  # noqa: E731

    regular = _num(g("regular_price_cad"))
    autopay = _num(g("autopay_price_cad"))
    bundle = _num(g("bundle_price_cad"))
    promo = _num(g("promo_price_cad"))
    monthly = _num(g("monthly_price_cad"))
    legacy = _num(g("price_cad"))

    starts = _dt(g("promo_starts_at"))
    ends = _dt(g("promo_ends_at"))
    expiry_known = g("promo_expiry_known")
    stated_savings = _num(g("promo_savings_cad"))

    has_promo = promo is not None
    expired = bool(ends and ends <= now)
    not_started = bool(starts and starts > now)
    active = has_promo and not expired and not not_started

    # --- build the tier list (cheapest-eligible first) --------------
    tiers: list[dict] = []
    if regular is not None:
        tiers.append({"amount": regular, "label": "regular", "conditions": []})
    if autopay is not None and autopay != regular:
        tiers.append({
            "amount": autopay, "label": "with AutoPay",
            "conditions": [g("autopay_conditions") or "automatic / pre-authorized payments"],
        })
    if bundle is not None:
        tiers.append({
            "amount": bundle, "label": "with bundle",
            "conditions": [g("bundle_conditions") or "requires a home-internet / streaming bundle"],
        })
    if active:
        pc = [g("promo_conditions")] if g("promo_conditions") else []
        if g("promo_stacks_conditions"):
            pc.append(g("promo_stacks_conditions"))
        if g("promo_new_customers_only"):
            pc.append("new customers only")
        if ends:
            pc.append(f"until {ends.date().isoformat()}")
        elif expiry_known is False:
            pc.append("limited time (no end date published)")
        tiers.append({"amount": promo, "label": "promotional", "conditions": pc})
    tiers.sort(key=lambda t: t["amount"])

    # --- universal / display / best-case ---------------------------
    universal = regular
    if universal is None and not (autopay or bundle or promo):
        # no tier model in play -> fall back to the simple fields
        universal = monthly if monthly is not None else legacy

    priced = [t["amount"] for t in tiers] or [
        v for v in (regular, autopay, bundle, promo, monthly, legacy) if v is not None
    ]
    best_case = min(priced) if priced else None

    has_conditional = any(t["conditions"] for t in tiers) or bool(bundle or (promo and (
        g("promo_stacks_conditions") or g("promo_new_customers_only")
    )))

    if universal is not None:
        display = universal
        note = None
    elif priced:
        display = max(priced)  # be conservative -- never present a conditional price as universal
        cheapest = min(tiers, key=lambda t: t["amount"]) if tiers else None
        if cheapest and cheapest["conditions"]:
            note = (
                f"${cheapest['amount']:g}/mo requires: "
                + "; ".join(c for c in cheapest["conditions"] if c)
                + f". Unconditional price not recorded (showing ${display:g})."
            )
        else:
            note = "unconditional price not recorded"
    else:
        display = None
        note = "no price recorded"

    # --- offer state ---------------------------------------------
    baseline = universal if universal is not None else display
    is_offer = bool(active and baseline is not None and promo is not None and promo < baseline)
    offer_conditional = bool(is_offer and (
        g("promo_stacks_conditions") or g("promo_new_customers_only") or bundle is not None
    ))
    savings = None
    if is_offer:
        savings = stated_savings if stated_savings is not None else round(baseline - promo, 2)

    offer_note = None
    if has_promo and expired:
        offer_note = f"promotional price expired {ends.date().isoformat()}; regular price applies"
    elif has_promo and not_started:
        offer_note = f"promotion starts {starts.date().isoformat()}"
    elif has_promo and expiry_known is False:
        offer_note = "promotion is time-limited but no end date is published"
    elif has_promo and expiry_known is None and ends is None:
        offer_note = "promotion expiry not stated by the source"

    # what a DEFAULT user (no autopay/bundle) pays right now: a universal active
    # promo lowers it; a conditional promo does not.
    if is_offer and not offer_conditional:
        effective = promo
    else:
        effective = universal if universal is not None else display

    # --- period normalization ---------------------------------------
    # Ranking must never sort/score on a raw annual total as if it were a
    # monthly price (e.g. Chatr's $159/12mo plan is NOT a $159/mo plan).
    period = g("price_period")
    term_months = g("term_months")
    if universal is not None and period == "annual" and term_months:
        monthly_equivalent = round(universal / term_months, 2)
    else:
        monthly_equivalent = universal

    return PriceView(
        universal_price_cad=universal,
        display_price_cad=display,
        best_case_price_cad=best_case,
        tiers=tiers,
        has_conditional_discounts=has_conditional,
        price_note=note,
        has_promo=has_promo,
        offer_active=active,
        offer_expired=expired,
        expiry_known=expiry_known,
        is_current_offer=is_offer,
        offer_is_conditional=offer_conditional,
        savings_cad=savings,
        offer_note=offer_note,
        effective_price_cad=effective,
        monthly_equivalent_price_cad=monthly_equivalent,
        billing_period=period,
        term_months=term_months,
        upfront_price_cad=universal if period == "annual" else None,
    )
