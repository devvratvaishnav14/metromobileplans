"""Deterministic V1 ranking engine.

Implements the design frozen in ``docs/ranking-engine-design.md`` plus the
corrections agreed on top of it (Technology renamed from Network, the
log-based Data formula, the rescaled Offer formula measured against a fixed
regular reference price, and the 3-part Features formula with no payment-
flexibility term). Nothing here is retuned independently of that approval --
if a component formula looks wrong, it's either a bug (report it) or a
deliberate, already-approved choice explained inline.

Everything is a plain function over ORM ``Plan`` rows + a :class:`RankingContext`.
No LLM, no hidden state: the same inputs always produce the same score and the
same explanation strings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Plan
from .pricing import PriceView, price_view
from .serializers import effective_state

# --- presets -------------------------------------------------------------

OVERALL = "overall"
STUDENTS = "students"
CHEAPEST = "cheapest"
MOST_DATA = "most_data"
OFFERS = "offers"
PRESETS = (OVERALL, STUDENTS, CHEAPEST, MOST_DATA, OFFERS)

# Frozen weight matrix -- component -> weight (must sum to 100 per preset).
WEIGHTS: dict[str, dict[str, float]] = {
    OVERALL:   {"price": 30, "data": 30, "technology": 10, "features": 15, "roaming": 5, "offer": 10},
    STUDENTS:  {"price": 35, "data": 25, "technology": 10, "features": 10, "roaming": 5, "offer": 15},
    CHEAPEST:  {"price": 100, "data": 0, "technology": 0, "features": 0, "roaming": 0, "offer": 0},
    MOST_DATA: {"price": 0, "data": 100, "technology": 0, "features": 0, "roaming": 0, "offer": 0},
    OFFERS:    {"price": 20, "data": 15, "technology": 5, "features": 5, "roaming": 5, "offer": 50},
}
COMPONENT_ORDER = ("price", "data", "technology", "features", "roaming", "offer")

# --- calibration constants (frozen) --------------------------------------

PRICE_FLOOR = 10.0
PRICE_CEIL = 120.0

DATA_LOG_SCALE = 95.0
DATA_LOG_DENOM = math.log(251)  # ln(1 + 250), 250GB is the largest finite tier seen

TECH_TIER = {"5G+": 100.0, "5G": 85.0, "4G LTE": 60.0, "4G": 60.0, "3G": 30.0}

FEATURE_WEIGHTS = {"talk": 0.55, "text": 0.30, "hotspot": 0.15}

OFFER_PERCENT_BENCHMARK = 0.30   # ~30% off = an extremely strong percentage discount
OFFER_DOLLAR_BENCHMARK = 25.0    # ~$25/mo off = an extremely strong absolute discount
OFFER_DURATION_BONUS_CAP = 10.0


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


# --- ranking context -------------------------------------------------------

@dataclass(frozen=True)
class RankingContext:
    """User-confirmed eligibility / preference flags. Both default False --
    never inferred from which preset was picked. New eligibility/preference
    flags belong here; nothing in the scoring functions below should need to
    change shape when one is added."""

    student_eligible: bool = False
    autopay_willing: bool = False
    municipality: str | None = None  # accepted, currently has zero scoring effect


# --- V1 customization: hard candidate-pool filters -----------------------

_FIVE_G_TECH = frozenset({"5G", "5G+"})
_PLAN_TYPES = frozenset({"prepaid", "postpaid"})


@dataclass(frozen=True)
class CustomFilters:
    """Optional V1 hard filters. Every field left at its default = inactive, and
    an all-default ``CustomFilters`` MUST NOT change any ranking (backward
    compatibility). Filters only remove plans from the candidate pool -- they
    never touch a score or a weight.

    Applied AFTER eligibility gating and price resolution, BEFORE preset scoring
    (so budget compares against the price actually applicable to this user)."""

    max_monthly_price_cad: float | None = None
    min_data_gb: float | None = None
    plan_type: str | None = None  # "prepaid" | "postpaid"  ("any"/None = no filter)
    require_5g: bool = False
    require_can_us_mex: bool = False
    require_international_roaming: bool = False

    @property
    def any_active(self) -> bool:
        return (
            self.max_monthly_price_cad is not None
            or self.min_data_gb is not None
            or self.plan_type in _PLAN_TYPES
            or self.require_5g
            or self.require_can_us_mex
            or self.require_international_roaming
        )


def passes_filters(
    plan: Plan,
    price_used_cad: float | None,
    gb: float | str | None,
    filters: CustomFilters,
) -> bool:
    """True if ``plan`` survives every active hard filter. ``price_used_cad`` is
    the monthly-equivalent price applicable to this user (universal, or a
    verified student / AutoPay tier once confirmed); ``gb`` is domestic
    full-speed data only ("UNLIMITED" sentinel / finite GB / 0.0 / None)."""

    # 1. maximum monthly budget -- compares the APPLICABLE monthly-equivalent
    #    price (annual plans already normalized: Chatr's $159/12mo compares as
    #    $13.25/mo, not $159).
    if filters.max_monthly_price_cad is not None:
        if price_used_cad is None or price_used_cad > filters.max_monthly_price_cad:
            return False

    # 2. minimum domestic full-speed data (never roaming / Roam Beyond GB).
    if filters.min_data_gb is not None:
        if gb == "UNLIMITED":
            pass  # genuinely-unlimited full-speed satisfies any finite minimum
        elif gb is None:
            return False  # can't confirm a hard requirement we haven't verified
        elif float(gb) < filters.min_data_gb:
            return False  # includes the known-no-data (0.0) case for any min > 0

    # 3. plan type -- only when the verified normalized field states it.
    if filters.plan_type in _PLAN_TYPES:
        if plan.plan_type != filters.plan_type:
            return False

    # 4. 5G hard requirement -- unknown technology does NOT qualify.
    if filters.require_5g and plan.network_technology not in _FIVE_G_TECH:
        return False

    # 5. Canada-US-Mexico -- both must be verified true (never inferred).
    if filters.require_can_us_mex and not (
        plan.includes_us is True and plan.includes_mexico is True
    ):
        return False

    # 6. international roaming -- verified true only.
    if filters.require_international_roaming and plan.international_roaming is not True:
        return False

    return True


# --- period-normalized price resolution ------------------------------------

def _tier_monthly_equivalent(amount: float | None, plan: Plan) -> float | None:
    if amount is None:
        return None
    amount = float(amount)  # ORM Numeric columns come back as decimal.Decimal
    if plan.price_period == "annual" and plan.term_months:
        return round(amount / plan.term_months, 2)
    return amount


def _is_autopay_only_conditional(plan: Plan) -> bool:
    """True if AutoPay is the plan's ONLY conditional tier (no bundle, no promo)
    -- the one case where `autopay_willing=True` alone is enough to swap the
    price used for ranking. Mixed tiers stay conditional-only (see design §8)."""
    return (
        plan.autopay_price_cad is not None
        and plan.bundle_price_cad is None
        and plan.promo_price_cad is None
    )


def _is_student_unlocked(plan: Plan) -> bool:
    """A restricted plan enters the student candidate pool when it is flagged
    student_offer=True, or -- for the known Koodo importer gap documented in
    the design report (§8) -- its eligibility_conditions text mentions
    "student". This fallback is a deliberate, already-flagged compromise, not
    a new guess introduced here."""
    if not plan.eligibility_restricted:
        return False
    if plan.student_offer:
        return True
    conditions = (plan.eligibility_conditions or "").lower()
    return "student" in conditions


@dataclass
class PriceResolution:
    price_used_cad: float | None            # monthly-equivalent price used for THIS user
    regular_reference_price_cad: float | None  # fixed, unconditional monthly-equivalent -- Offer's baseline
    applicable_tier_label: str | None        # which tier price_used_cad came from, if not "regular"
    commitment: dict | None                  # {upfront_cad, term_months} when annual, else None


def resolve_price(plan: Plan, pv: PriceView, ctx: RankingContext) -> PriceResolution:
    """Separates the price used for THIS user's Price component from the fixed
    regular reference price the Offer component must always measure against --
    confirming eligibility must never change what "$X saved" means (see
    design §8 / the Freedom-student worked example)."""

    regular_reference = pv.monthly_equivalent_price_cad
    commitment = (
        {"upfront_cad": pv.upfront_price_cad, "term_months": pv.term_months}
        if pv.billing_period == "annual"
        else None
    )

    price_used = regular_reference
    tier_label: str | None = None

    if ctx.student_eligible and _is_student_unlocked(plan) and plan.promo_price_cad is not None:
        price_used = _tier_monthly_equivalent(plan.promo_price_cad, plan)
        tier_label = "promotional (student)"
    elif ctx.autopay_willing and _is_autopay_only_conditional(plan):
        price_used = _tier_monthly_equivalent(plan.autopay_price_cad, plan)
        tier_label = "with AutoPay"

    return PriceResolution(
        price_used_cad=price_used,
        regular_reference_price_cad=regular_reference,
        applicable_tier_label=tier_label,
        commitment=commitment,
    )


# --- component scores (each 0-100, or None if genuinely unknown) ----------

def price_score(price: float | None) -> float | None:
    if price is None:
        return None
    return 100.0 * _clamp((PRICE_CEIL - price) / (PRICE_CEIL - PRICE_FLOOR))


def data_gb(plan: Plan) -> float | str | None:
    """UNLIMITED sentinel, a finite GB number, 0.0 for a known no-data plan, or
    None if genuinely unresolvable. Domestic full-speed allowance ONLY -- never
    roaming/hotspot/bonus GB (design §4)."""
    if plan.data_unlimited_is_full_speed:
        return "UNLIMITED"
    if plan.data_full_speed_gb is not None:
        return plan.data_full_speed_gb
    if plan.data_total_gb is not None:
        return plan.data_total_gb
    if plan.data_unlimited is False:
        return 0.0
    return None


def data_score(gb: float | str | None) -> float | None:
    if gb is None:
        return None
    if gb == "UNLIMITED":
        return 100.0
    if gb == 0:
        return 0.0
    return min(DATA_LOG_SCALE, DATA_LOG_SCALE * math.log(1 + gb) / DATA_LOG_DENOM)


def technology_score(plan: Plan) -> float | None:
    """Measures advertised network TECHNOLOGY (5G/4G/etc), not coverage or
    quality -- deliberately renamed from "Network" to avoid implying either."""
    return TECH_TIER.get(plan.network_technology)


def features_score(plan: Plan) -> float:
    """3-part composite: Canada-wide calling / unlimited text / hotspot. No
    payment-flexibility term (removed -- it produced zero variance in V1 and
    silently inflated every plan's score; see design correction). Commitment
    facts (upfront $, term) are disclosed separately as metadata, never scored."""
    parts: dict[str, float] = {}

    if plan.canada_wide_calling is True:
        parts["talk"] = 100.0
    elif plan.canada_wide_calling is False:
        parts["talk"] = 40.0
    # else: unknown -- renormalize (excluded from parts)

    if plan.unlimited_text is True:
        parts["text"] = 100.0
    elif plan.unlimited_text is False:
        parts["text"] = 40.0

    parts["hotspot"] = 100.0 if plan.hotspot is True else 50.0  # neutral if unknown/false

    weight_sum = sum(FEATURE_WEIGHTS[k] for k in parts)
    return sum(parts[k] * FEATURE_WEIGHTS[k] for k in parts) / weight_sum


def roaming_score(plan: Plan) -> float:
    """Coverage SCOPE only -- never roaming data quantities. `None` on
    includes_us/includes_mexico/international_roaming reads as a known "not
    advertised" fact (capture discipline requires drafters to only set these
    when the source states them), not a missing value -- see design §5.6."""
    if plan.includes_us and plan.includes_mexico:
        return 100.0
    if plan.includes_us and not plan.includes_mexico:
        return 75.0
    if plan.international_roaming and not plan.includes_us and not plan.includes_mexico:
        return 80.0
    return 0.0


@dataclass
class OfferDetail:
    tier_label: str
    tier_amount_cad: float
    dollar_savings_cad: float
    percent_savings: float
    percent_score: float
    dollar_score: float
    base_offer_score: float
    condition_ease: float
    expiry_ease: float
    duration_bonus: float
    offer_score: float


def _condition_ease(tier_label: str, conditions_text: str, ctx: RankingContext) -> float:
    conds = conditions_text.lower()
    if tier_label == "with bundle":
        return 0.40
    if tier_label == "with AutoPay":
        return 1.00 if ctx.autopay_willing else 0.90
    if tier_label == "promotional":
        if "student" in conds:
            # only reachable once student_eligible=True unlocked the tier at all
            return 0.95
        if "autopay" in conds:
            return 0.85 if ctx.autopay_willing else 0.70
        return 0.80
    return 0.70  # mixed / unspecified conditional tier


def _expiry_ease(tier: dict, plan: Plan) -> float:
    if tier["label"] != "promotional":
        return 1.0
    if plan.promo_ends_at:
        return 1.0
    if plan.promo_expiry_known is False:
        return 0.85
    return 1.0


def offer_score(plan: Plan, pv: PriceView, ctx: RankingContext) -> tuple[float, OfferDetail | None]:
    """Always measured against the fixed, unconditional regular reference
    price -- confirming eligibility for a lower Price-component price must
    NEVER zero out a verified saving (design §Offer / Freedom-student example)."""
    reg = pv.monthly_equivalent_price_cad
    if not reg:
        return 0.0, None

    best_score = 0.0
    best_detail: OfferDetail | None = None
    for tier in pv.tiers:
        if tier["label"] == "regular":
            continue
        amount = _tier_monthly_equivalent(tier["amount"], plan)
        dollar_savings = reg - amount
        if dollar_savings <= 0:
            continue
        percent_savings = dollar_savings / reg
        percent_score = 100.0 * _clamp(percent_savings / OFFER_PERCENT_BENCHMARK)
        dollar_score = 100.0 * _clamp(dollar_savings / OFFER_DOLLAR_BENCHMARK)
        base = 0.60 * percent_score + 0.40 * dollar_score

        conds_text = " ".join(c for c in (tier.get("conditions") or []) if c)
        ease = _condition_ease(tier["label"], conds_text, ctx)
        expiry = _expiry_ease(tier, plan)
        months = plan.promo_duration_months or 0
        duration_bonus = min(OFFER_DURATION_BONUS_CAP, months / 3.0)

        value = _clamp(base * ease * expiry + duration_bonus, 0.0, 100.0)
        if value > best_score:
            best_score = value
            best_detail = OfferDetail(
                tier_label=tier["label"],
                tier_amount_cad=amount,
                dollar_savings_cad=round(dollar_savings, 2),
                percent_savings=round(percent_savings, 4),
                percent_score=round(percent_score, 1),
                dollar_score=round(dollar_score, 1),
                base_offer_score=round(base, 1),
                condition_ease=ease,
                expiry_ease=expiry,
                duration_bonus=round(duration_bonus, 1),
                offer_score=round(value, 2),
            )
    return best_score, best_detail


# --- weighted total, with proportional redistribution for missing components

def weighted_total(components: dict[str, float | None], weights: dict[str, float]) -> float | None:
    present = {k: v for k, v in components.items() if v is not None}
    weight_sum = sum(weights[k] for k in present)
    if weight_sum == 0:
        return None
    return round(sum(components[k] * weights[k] for k in present) / weight_sum, 2)


# --- candidate pool ---------------------------------------------------------

def candidate_pool(session: Session, ctx: RankingContext, now) -> list[Plan]:
    plans = session.scalars(select(Plan)).all()
    pool: list[Plan] = []
    for p in plans:
        freshness, status, rankable = effective_state(p, now)
        if status == "invalid" or freshness == "stale":
            continue
        if rankable:
            pool.append(p)
        elif ctx.student_eligible and p.eligibility_restricted and _is_student_unlocked(p):
            # a verified-but-restricted plan re-enters the pool once the matching
            # eligibility flag is confirmed -- never automatically, never for a
            # flag the user hasn't actually set (design §4 / §8).
            if status in ("verified", "secondary_confirmed"):
                pool.append(p)
    return pool


# --- output ------------------------------------------------------------

@dataclass
class RankedPlan:
    rank: int
    plan: Plan
    final_score: float
    price_score: float | None
    data_score: float | None
    technology_score: float | None
    features_score: float | None
    roaming_score: float | None
    offer_score: float | None
    price_used_cad: float | None
    regular_reference_price_cad: float | None
    applicable_tier_label: str | None
    monthly_equivalent_price_cad: float | None
    commitment: dict | None
    offer_detail: OfferDetail | None
    eligibility_note: str | None
    reasons: list[str] = field(default_factory=list)


def _gb_label(gb: float | str | None) -> str:
    if gb == "UNLIMITED":
        return "Unlimited"
    if gb is None:
        return "an unstated amount of"
    return f"{gb:g}GB"


def build_reasons(
    plan: Plan,
    price_used: float | None,
    d_gb,
    d_score: float | None,
    tech: float | None,
    roam: float | None,
    offer: float,
    offer_detail: OfferDetail | None,
) -> list[str]:
    """Short, deterministic, template-generated reasons -- never free-text from
    an LLM. Picks the most notable true facts, in a fixed priority order."""
    reasons: list[str] = []

    if d_score is not None and d_score >= 75:
        reasons.append(f"Excellent data value · {_gb_label(d_gb)} at ${price_used:.2f}/mo")
    elif price_used is not None and d_gb not in (None,):
        reasons.append(f"{_gb_label(d_gb)} at ${price_used:.2f}/mo")

    # a verified discount is one of the most notable facts about a plan --
    # surfaced right after data/price so it isn't crowded out of the top 3.
    if offer > 0 and offer_detail is not None:
        reasons.append(
            f"Verified saving of ${offer_detail.dollar_savings_cad:.2f}/mo "
            f"({offer_detail.percent_savings * 100:.0f}%) {offer_detail.tier_label}"
        )

    if roam == 100:
        reasons.append("Canada-US-Mexico roaming included")
    elif roam == 75:
        reasons.append("US roaming included")
    elif roam == 80:
        reasons.append("International roaming included")

    if tech is not None and tech >= 85:
        reasons.append(f"{plan.network_technology} network")

    return reasons[:3]


def _most_data_tiebreak(plan: Plan, gb) -> int:
    continues = (
        gb != "UNLIMITED"
        and plan.data_unlimited is True
        and not plan.data_hard_cap
    )
    return 0 if continues else 1


def _secondary_component_for(weights: dict[str, float]) -> str | None:
    """The preset's own second-highest-weighted component, per design §10.
    Named explicitly for the two single-axis presets (Cheapest -> Data,
    Most Data -> Price) since falling back to the same, already-100%-weighted
    axis would be a no-op tie-break; derived generically otherwise."""
    if weights is WEIGHTS[CHEAPEST]:
        return "data"
    if weights is WEIGHTS[MOST_DATA]:
        return "price"
    ordered = sorted(COMPONENT_ORDER, key=lambda k: -weights[k])
    return ordered[1] if len(ordered) > 1 else None


@dataclass
class RankingResult:
    results: list[RankedPlan]
    candidate_count: int  # size of the scored pool BEFORE truncating to `limit`
    # candidates after verified/current + eligibility gating, BEFORE the custom
    # hard filters -- lets the caller explain "your filters removed N plans".
    pre_filter_count: int = 0


def rank_plans(
    session: Session,
    preset: str,
    ctx: RankingContext,
    now,
    limit: int = 5,
    filters: CustomFilters | None = None,
) -> RankingResult:
    if preset not in PRESETS:
        raise ValueError(f"unknown ranking preset: {preset!r}")
    weights = WEIGHTS[preset]
    filters = filters or CustomFilters()

    pool = candidate_pool(session, ctx, now)
    scored: list[tuple[float | None, Plan, dict]] = []

    for plan in pool:
        pv = price_view(plan, now)
        resolution = resolve_price(plan, pv, ctx)
        gb = data_gb(plan)

        # custom hard filters -- applied AFTER price resolution, BEFORE scoring.
        if not passes_filters(plan, resolution.price_used_cad, gb, filters):
            continue

        o_score, o_detail = offer_score(plan, pv, ctx)

        components = {
            "price": price_score(resolution.price_used_cad),
            "data": data_score(gb),
            "technology": technology_score(plan),
            "features": features_score(plan),
            "roaming": roaming_score(plan),
            "offer": o_score,
        }

        if preset == OFFERS and o_score <= 0:
            continue  # Best Current Offers requires a genuine, verified saving

        total = weighted_total(components, weights)
        scored.append((total, plan, {
            "components": components, "pv": pv, "resolution": resolution,
            "gb": gb, "offer_detail": o_detail,
        }))

    secondary = _secondary_component_for(weights)

    def sort_key(item):
        total, plan, ctx_data = item
        components = ctx_data["components"]
        key = [-(total if total is not None else -1.0)]
        if preset == MOST_DATA:
            key.append(_most_data_tiebreak(plan, ctx_data["gb"]))
            price = ctx_data["resolution"].price_used_cad
            key.append(price if price is not None else float("inf"))
        elif secondary:
            key.append(-(components.get(secondary) or 0))
        key.append(plan.last_verified_at.isoformat() if plan.last_verified_at else "")
        key.append(0 if ctx_data["pv"].is_current_offer else 1)
        key.append(plan.external_id)
        return tuple(key)

    scored.sort(key=sort_key)

    results: list[RankedPlan] = []
    for i, (total, plan, ctx_data) in enumerate(scored[:limit], start=1):
        components = ctx_data["components"]
        resolution = ctx_data["resolution"]
        eligibility_note = None
        if plan.eligibility_restricted:
            eligibility_note = plan.eligibility_conditions

        reasons = build_reasons(
            plan,
            resolution.price_used_cad,
            ctx_data["gb"],
            components["data"],
            components["technology"],
            components["roaming"],
            components["offer"] or 0.0,
            ctx_data["offer_detail"],
        )

        results.append(RankedPlan(
            rank=i,
            plan=plan,
            final_score=total if total is not None else 0.0,
            price_score=components["price"],
            data_score=components["data"],
            technology_score=components["technology"],
            features_score=components["features"],
            roaming_score=components["roaming"],
            offer_score=components["offer"],
            price_used_cad=resolution.price_used_cad,
            regular_reference_price_cad=resolution.regular_reference_price_cad,
            applicable_tier_label=resolution.applicable_tier_label,
            monthly_equivalent_price_cad=ctx_data["pv"].monthly_equivalent_price_cad,
            commitment=resolution.commitment,
            offer_detail=ctx_data["offer_detail"],
            eligibility_note=eligibility_note,
            reasons=reasons,
        ))
    return RankingResult(
        results=results,
        candidate_count=len(scored),
        pre_filter_count=len(pool),
    )
