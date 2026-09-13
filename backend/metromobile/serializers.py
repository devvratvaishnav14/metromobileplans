"""ORM -> API dict. Keeps :mod:`metromobile.api` thin.

Two things are recomputed at serve time so stored rows can't get stale-wrong:
  * freshness / ranking eligibility (a manually verified plan past its window
    reports as ``stale`` and non-rankable even before a sweep runs)
  * current-offer status (an expired promotion never shows as a current offer and
    its price never counts)
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .freshness import AGING, FRESH, STALE, freshness_state, humanize_age
from .models import Plan, Provider, RefreshRun
from .pricing import price_view
from .schemas import MetaOut, PlanIssueOut, PlanOut, PlansResponse, ProviderOut

_MODE_LABEL = {
    "official_automated": "Official source, fetched automatically",
    "official_manual": "Official source, manually verified",
    "trusted_secondary": "Trusted third-party source",
}

# worst (least fresh) wins when rolling per-plan freshness up into one overall value
_FRESHNESS_SEVERITY = {FRESH: 0, AGING: 1, STALE: 2}


def effective_state(plan: Plan, now: dt.datetime) -> tuple[str, str, bool]:
    """(freshness, verification_status, is_rankable) after re-checking staleness."""
    settings = get_settings()
    freshness = freshness_state(
        plan.last_verified_at, source_mode=plan.source_mode, now=now, settings=settings
    )
    status = plan.verification_status
    rankable = plan.is_rankable
    if freshness == STALE and status in ("verified", "secondary_confirmed"):
        status = "stale"
    if freshness == STALE:
        rankable = False
    return freshness, status, rankable


def plan_out(plan: Plan, provider_name: str, now: dt.datetime) -> PlanOut:
    out = PlanOut.model_validate(plan)

    freshness, status, rankable = effective_state(plan, now)
    age = humanize_age(plan.last_verified_at, now=now)
    if status == "stale":
        label = f"Verification stale — needs re-verification (last verified {age})"
    elif status == "secondary_confirmed":
        # a trusted_secondary record with no official cross-check: never "Verified"
        label = f"Secondary source · fetched {age}"
    elif status == "provisional":
        label = f"Not officially verified — incomplete data · fetched {age}"
    elif status == "invalid":
        label = f"Failed verification · last checked {age}"
    elif plan.verified_by:
        label = f"Verified by {plan.verified_by} {age}"
    else:
        label = f"Verified {age}"

    pv = price_view(plan, now)
    events = sorted(plan.verification_events, key=lambda e: e.event_at)

    out.provider_name = provider_name
    out.source_mode_label = _MODE_LABEL.get(plan.source_mode, plan.source_mode)
    out.verification_status = status
    out.stored_verification_status = plan.verification_status
    out.is_rankable = rankable
    out.freshness = freshness
    out.freshness_label = label
    out.verification_event_count = len(events)
    out.first_verified_at = events[0].event_at if events else plan.first_seen_at

    out.universal_price_cad = pv.universal_price_cad
    out.display_price_cad = pv.display_price_cad
    out.best_case_price_cad = pv.best_case_price_cad
    out.price_tiers = pv.tiers
    out.has_conditional_discounts = pv.has_conditional_discounts
    out.price_note = pv.price_note
    out.effective_price_cad = pv.effective_price_cad
    out.is_current_offer = pv.is_current_offer
    out.offer_is_conditional = pv.offer_is_conditional
    out.offer_active = pv.offer_active
    out.offer_expired = pv.offer_expired
    out.offer_savings_cad = pv.savings_cad
    out.offer_note = pv.offer_note

    out.issues = [
        PlanIssueOut(severity=i.severity, field=i.field, message=i.message)
        for i in sorted(plan.issues, key=lambda x: x.severity)
    ]
    return out


def _sort_key(p: PlanOut) -> tuple:
    # sort on the price a default (unconditional) user would pay
    price = p.display_price_cad if p.display_price_cad is not None else p.effective_price_cad
    return (0 if price is not None else 1, price or 0.0, p.plan_name or "")


def _overall_freshness(states: dict[int, tuple[str, str, bool]]) -> str | None:
    """Roll up the per-plan (source-mode-aware) freshness values already computed
    in ``states`` into a single worst-case label.

    This must NOT re-derive freshness from a raw timestamp: a manually verified
    plan is legitimately "fresh" for weeks under its own re-verify window, but
    judging that same timestamp against the automated-source default window
    (hours, not weeks) would wrongly report the whole catalogue "stale" even
    though every individual plan is current. Reusing ``states`` guarantees this
    always matches each plan's own ``freshness_label``.
    """
    freshness_values = [freshness for freshness, _status, _rankable in states.values()]
    if not freshness_values:
        return None
    return max(freshness_values, key=lambda f: _FRESHNESS_SEVERITY[f])


def build_meta(session: Session, municipality: str | None, now: dt.datetime) -> MetaOut:
    providers = session.scalars(select(Provider)).all()
    plans = session.scalars(select(Plan)).all()

    states = {p.id: effective_state(p, now) for p in plans}
    verified_times = [p.last_verified_at for p in plans]
    oldest = min(verified_times) if verified_times else None
    last_run = session.scalar(
        select(RefreshRun)
        .where(RefreshRun.status.in_(("success", "partial")))
        .order_by(RefreshRun.finished_at.desc())
    )
    last_refreshed = last_run.finished_at if last_run else None

    overall = _overall_freshness(states)
    label = (
        f"Current plan data · last refreshed {humanize_age(last_refreshed, now=now)}"
        if last_refreshed
        else "No plan data has been fetched yet"
    )

    current = [p for p in plans if states[p.id][1] not in ("invalid", "stale")]
    current_offers = sum(
        1
        for p in plans
        if states[p.id][1] not in ("invalid", "stale") and price_view(p, now).is_current_offer
    )

    mode_counts: dict[str, int] = {}
    for p in plans:
        mode_counts[p.source_mode] = mode_counts.get(p.source_mode, 0) + 1

    notes = [
        "Plans come from official carrier sources and are re-verified on a "
        "schedule, not in real time. Each plan shows when it was last verified.",
        "The selected municipality does not change plan ordering or eligibility. "
        "There is no area-specific network scoring.",
        "Regular and conditional (AutoPay / bundle / promotional) prices are "
        "stored separately; an expired promotion is never shown as a current offer.",
    ]

    return MetaOut(
        municipality=municipality,
        municipality_affects_results=False,
        generated_at=now,
        data_last_refreshed_at=last_refreshed,
        data_oldest_verified_at=oldest,
        freshness=overall,
        freshness_label=label,
        plan_count=len(plans),
        current_plan_count=len(current),
        rankable_count=sum(1 for p in plans if states[p.id][2]),
        current_offer_count=current_offers,
        flagged_count=sum(1 for p in plans if not states[p.id][2]),
        provider_count=len(providers),
        source_mode_counts=mode_counts,
        providers=[
            ProviderOut(
                slug=pr.slug,
                display_name=pr.display_name,
                network=pr.network,
                plan_model=pr.plan_model,
                default_source_mode=pr.default_source_mode,
                source_url=next((s.url for s in pr.sources), ""),
                source_kind=next((s.kind for s in pr.sources), ""),
            )
            for pr in providers
        ],
        notes=notes,
    )


def build_plans_response(
    session: Session, municipality: str | None, now: dt.datetime
) -> PlansResponse:
    provider_names = {p.slug: p.display_name for p in session.scalars(select(Provider)).all()}
    plans = session.scalars(select(Plan)).all()
    out = [plan_out(p, provider_names.get(p.provider_slug, p.provider_slug), now) for p in plans]
    out.sort(key=_sort_key)
    return PlansResponse(
        meta=build_meta(session, municipality, now),
        plans=out,
        scores=[],
        profiles=[],
    )
