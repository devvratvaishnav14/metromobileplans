"""FastAPI app. Two real endpoints for the frontend + a health check."""

from __future__ import annotations

import datetime as dt

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Provider

from . import __version__
from .config import get_settings
from .db import get_session
from .ranking import PRESETS, CustomFilters, RankingContext, rank_plans
from .schemas import (
    FiltersApplied,
    MetaOut,
    OfferDetailOut,
    PlansResponse,
    RankedPlanOut,
    RankingResponse,
)
from .serializers import build_meta, build_plans_response, plan_out

app = FastAPI(title="metro-mobile-plans backend", version=__version__)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
@app.get("/healthz")
def health() -> dict:
    """Liveness probe. Deliberately does not touch the database or leak config."""
    return {"status": "ok", "version": __version__}


@app.get("/api/plans", response_model=PlansResponse)
def get_plans(
    municipality: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> PlansResponse:
    now = dt.datetime.now(dt.timezone.utc)
    return build_plans_response(session, municipality, now)


@app.get("/api/meta", response_model=MetaOut)
def get_meta(
    municipality: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> MetaOut:
    now = dt.datetime.now(dt.timezone.utc)
    return build_meta(session, municipality, now)


_PLAN_TYPE_CHOICES = ("any", "prepaid", "postpaid")


@app.get("/api/rank", response_model=RankingResponse)
def get_ranking(
    preset: str = Query(default="overall"),
    municipality: str | None = Query(default=None),
    student_eligible: bool = Query(default=False),
    # Broadly-available AutoPay / Digital Discount pricing (see
    # `_is_autopay_only_conditional`) is used by default; pass
    # autopay_willing=false explicitly to opt out and see regular pricing.
    autopay_willing: bool = Query(default=True),
    # --- V1 customization: optional hard filters (all default = no change) ---
    max_monthly_price_cad: float | None = Query(default=None, gt=0),
    min_data_gb: float | None = Query(default=None, ge=0),
    plan_type: str | None = Query(default=None),
    require_5g: bool = Query(default=False),
    require_can_us_mex: bool = Query(default=False),
    require_international_roaming: bool = Query(default=False),
    limit: int = Query(default=5, ge=1, le=50),
    session: Session = Depends(get_session),
) -> RankingResponse:
    if preset not in PRESETS:
        raise HTTPException(status_code=400, detail=f"unknown preset {preset!r}; choose one of {PRESETS}")
    if plan_type is not None and plan_type not in _PLAN_TYPE_CHOICES:
        raise HTTPException(
            status_code=400,
            detail=f"plan_type must be one of {_PLAN_TYPE_CHOICES}",
        )

    now = dt.datetime.now(dt.timezone.utc)
    ctx = RankingContext(
        student_eligible=student_eligible,
        autopay_willing=autopay_willing,
        municipality=municipality,
    )
    normalized_plan_type = plan_type if plan_type in ("prepaid", "postpaid") else None
    filters = CustomFilters(
        max_monthly_price_cad=max_monthly_price_cad,
        min_data_gb=min_data_gb,
        plan_type=normalized_plan_type,
        require_5g=require_5g,
        require_can_us_mex=require_can_us_mex,
        require_international_roaming=require_international_roaming,
    )
    provider_names = {p.slug: p.display_name for p in session.scalars(select(Provider)).all()}
    ranking = rank_plans(session, preset, ctx, now, limit=limit, filters=filters)

    results = [
        RankedPlanOut(
            rank=r.rank,
            plan_id=r.plan.id,
            provider_slug=r.plan.provider_slug,
            provider_name=provider_names.get(r.plan.provider_slug, r.plan.provider_slug),
            external_id=r.plan.external_id,
            plan_name=r.plan.plan_name,
            plan=plan_out(r.plan, provider_names.get(r.plan.provider_slug, r.plan.provider_slug), now),
            final_score=r.final_score,
            price_score=r.price_score,
            data_score=r.data_score,
            technology_score=r.technology_score,
            features_score=r.features_score,
            roaming_score=r.roaming_score,
            offer_score=r.offer_score,
            price_used_cad=r.price_used_cad,
            regular_reference_price_cad=r.regular_reference_price_cad,
            applicable_tier_label=r.applicable_tier_label,
            monthly_equivalent_price_cad=r.monthly_equivalent_price_cad,
            commitment=r.commitment,
            offer_detail=OfferDetailOut(**vars(r.offer_detail)) if r.offer_detail else None,
            eligibility_note=r.eligibility_note,
            reasons=r.reasons,
        )
        for r in ranking.results
    ]

    return RankingResponse(
        preset=preset,
        municipality=municipality,
        municipality_affects_results=False,
        student_eligible=student_eligible,
        autopay_willing=autopay_willing,
        generated_at=now,
        candidate_count=ranking.candidate_count,
        pre_filter_candidate_count=ranking.pre_filter_count,
        filters_applied=FiltersApplied(
            max_monthly_price_cad=filters.max_monthly_price_cad,
            min_data_gb=filters.min_data_gb,
            plan_type=filters.plan_type,
            require_5g=filters.require_5g,
            require_can_us_mex=filters.require_can_us_mex,
            require_international_roaming=filters.require_international_roaming,
            student_eligible=student_eligible,
            autopay_willing=autopay_willing,
            any_active=filters.any_active,
        ),
        results=results,
    )
