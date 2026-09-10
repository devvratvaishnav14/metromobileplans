"""Validation + ranking-eligibility gate, aware of the source mode.

Hard errors (any mode): missing name / source / price, negative numbers.

Ranking eligibility -- a plan enters ranked results only when the factual fields a
ranking engine must not guess are all present AND the record is verified AND fresh:

    plan name, current effective price, data allowance / unlimited status,
    plan type, availability, source, verification timestamp

Per-mode rules:

* official_automated  -- complete + not stale  -> verified, rankable
* official_manual     -- complete + within the (strict) re-verify window -> verified,
                         rankable; past the window -> stale, NOT rankable until re-verified
* trusted_secondary   -- never "verified" on its own: complete + fresh -> secondary_confirmed,
                         confidence capped, NOT rankable unless policy allows it OR an
                         official cross-check exists (then it may be verified + rankable)
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from .config import Settings, get_settings
from .freshness import STALE, freshness_state
from .models import OFFICIAL_AUTOMATED, OFFICIAL_MANUAL, TRUSTED_SECONDARY
from .pricing import price_view
from .providers.base import NormalizedPlan

VERIFIED = "verified"
PROVISIONAL = "provisional"
SECONDARY_CONFIRMED = "secondary_confirmed"
STALE_STATUS = "stale"
INVALID = "invalid"


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    field: str | None
    message: str


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)
    confidence: float = 1.0
    is_rankable: bool = True
    verification_status: str = VERIFIED
    freshness: str = "fresh"

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]


_GB_IN_NAME = re.compile(r"(\d+(?:\.\d+)?)\s*GB\b", re.I)


def validate_plan(
    plan: NormalizedPlan,
    *,
    provider_known: bool,
    source_url: str | None,
    source_mode: str = OFFICIAL_AUTOMATED,
    last_verified_at: dt.datetime | None = None,
    now: dt.datetime | None = None,
    official_crosscheck: bool = False,
    settings: Settings | None = None,
) -> ValidationResult:
    settings = settings or get_settings()
    now = now or dt.datetime.now(dt.timezone.utc)
    res = ValidationResult()

    def err(field_: str | None, msg: str) -> None:
        res.issues.append(Issue("error", field_, msg))

    def warn(field_: str | None, msg: str) -> None:
        res.issues.append(Issue("warning", field_, msg))

    # --- hard errors --------------------------------------------------
    if not provider_known:
        err("provider", "provider is not registered")
    if not plan.plan_name:
        err("plan_name", "plan has no name")
    if not source_url:
        err("source_url", "no source URL recorded")
    if source_mode not in (OFFICIAL_AUTOMATED, OFFICIAL_MANUAL, TRUSTED_SECONDARY):
        err("source_mode", f"unknown source mode {source_mode!r}")

    pv = price_view(plan, now)
    any_price = any(
        v is not None for v in (
            plan.regular_price_cad, plan.autopay_price_cad, plan.bundle_price_cad,
            plan.promo_price_cad, plan.monthly_price_cad, plan.price_cad,
        )
    )
    for f in ("regular_price_cad", "autopay_price_cad", "bundle_price_cad", "promo_price_cad",
              "monthly_price_cad", "price_cad"):
        v = getattr(plan, f, None)
        if v is not None and v < 0:
            err(f, "price is negative")
    if not any_price:
        err("price", "no price could be read from the source")
    # a plan whose only price is conditional (bundle / new-customer promo) cannot
    # rank as universally available -- ranking must use an unconditional price
    if any_price and pv.universal_price_cad is None:
        warn("regular_price_cad",
             "only conditional prices are recorded (bundle / promo / customer-specific) -- "
             "add the unconditional regular price before this plan can be ranked")
    # the price a neutral ranking would use
    effective_price = pv.universal_price_cad

    # --- data allowance sanity -------------------------------------
    data_known = plan.data_total_gb is not None or plan.data_unlimited is not None
    if plan.plan_name and _GB_IN_NAME.search(plan.plan_name) and plan.data_total_gb is None and not plan.data_unlimited:
        warn("data_total_gb", "plan name mentions GB but no data amount was parsed")
    if plan.data_total_gb is not None and plan.data_total_gb < 0:
        err("data_total_gb", "data amount is negative")

    # --- promotion sanity (expired / unknown expiry) ---------------
    if pv.has_promo and pv.offer_expired:
        warn("promo_ends_at", pv.offer_note or "promotional price has expired; regular price applies")
    elif pv.has_promo and pv.expiry_known in (None, False) and plan.promo_ends_at is None:
        warn("promo_expiry_known", pv.offer_note or "promotion expiry is not known")

    # --- ranking-eligibility fields --------------------------------
    missing = []
    if not plan.plan_name:
        missing.append("plan_name")
    if effective_price is None:
        missing.append("unconditional_price")
    if not data_known:
        missing.append("data_allowance")
    if not plan.plan_type:
        missing.append("plan_type")
    if not plan.availability:
        missing.append("availability")

    # --- freshness --------------------------------------------------
    lva = last_verified_at or now
    res.freshness = freshness_state(lva, source_mode=source_mode, now=now, settings=settings)
    is_stale = res.freshness == STALE

    # --- decide status / rankability ------------------------------
    if res.errors:
        res.verification_status = INVALID
        res.is_rankable = False
        res.confidence = 0.2
        return res

    if missing:
        res.verification_status = PROVISIONAL
        res.is_rankable = False
        res.confidence = round(max(0.3, 1.0 - 0.15 * len(missing)), 2)
        warn(None, "not rankable -- missing: " + ", ".join(missing))
        return res

    base_conf = round(max(0.5, 1.0 - 0.05 * len(res.issues)), 2)

    if is_stale:
        res.verification_status = STALE_STATUS
        res.is_rankable = False
        res.confidence = round(base_conf * 0.5, 2)
        warn(None, f"{source_mode} verification is stale -- re-verify to restore ranking eligibility")
        return res

    if source_mode == TRUSTED_SECONDARY and not official_crosscheck:
        res.verification_status = SECONDARY_CONFIRMED
        res.confidence = min(base_conf, settings.secondary_confidence_cap)
        res.is_rankable = bool(settings.secondary_ranking_allowed)
        if not res.is_rankable:
            warn(None, "secondary-only source -- not rankable without an official cross-check")
        return res

    # official_automated, official_manual, or secondary WITH cross-check
    res.verification_status = VERIFIED
    res.is_rankable = True
    res.confidence = base_conf
    if source_mode == TRUSTED_SECONDARY:
        res.confidence = min(base_conf, 0.85)  # cross-checked, but still not first-party

    # a restricted offer (partner / employer / exclusive) is a real, verified plan
    # but must NOT enter the default ranking -- only a user known to qualify can
    # rank it. Kept queryable/displayable; excluded from the neutral Top-N.
    if plan.eligibility_restricted:
        res.is_rankable = False
        warn(
            "eligibility_restricted",
            "restricted-eligibility offer -- excluded from the default ranking; "
            "rank only for a user who meets: "
            + (plan.eligibility_conditions or "the stated eligibility conditions"),
        )
    return res
