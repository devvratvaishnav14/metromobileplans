"""API response shapes. No ranking scores yet -- but every factual field the
future ranking / profiles / user-preference filtering will need is carried here.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class ProviderOut(BaseModel):
    slug: str
    display_name: str
    network: str | None
    plan_model: str | None
    default_source_mode: str | None
    source_url: str
    source_kind: str


class PlanIssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    severity: str
    field: str | None
    message: str


class PlanOut(BaseModel):
    # populated by model_validate(orm_plan); computed fields patched by the serializer
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_slug: str
    external_id: str
    plan_name: str | None
    plan_local_name: str | None

    # --- pricing tiers (direct from the record) -----------------
    price_period: str | None
    term_months: int | None
    regular_price_cad: float | None       # unconditional
    autopay_price_cad: float | None
    autopay_discount_cad: float | None
    autopay_conditions: str | None
    bundle_price_cad: float | None
    bundle_discount_cad: float | None
    bundle_conditions: str | None
    promo_price_cad: float | None
    promo_conditions: str | None
    promo_stacks_conditions: str | None
    pricing_notes: list | None
    monthly_price_cad: float | None
    price_cad: float | None

    # --- pricing (computed at serve time) ----------------------
    universal_price_cad: float | None = None   # what a neutral ranking uses
    display_price_cad: float | None = None      # shown by default (never a conditional price)
    best_case_price_cad: float | None = None    # lowest with all conditions + active promo
    price_tiers: list = []                      # [{amount, label, conditions}]
    has_conditional_discounts: bool = False
    price_note: str | None = None
    offer_is_conditional: bool = False          # the active promo also needs autopay/bundle

    # --- promotion (structured) --------------------------------
    promo_name: str | None
    promo_savings_cad: float | None
    promo_starts_at: dt.datetime | None
    promo_ends_at: dt.datetime | None
    promo_expiry_known: bool | None
    promo_duration_months: int | None
    promo_new_customers_only: bool | None
    promo_online_only: bool | None
    promo_autopay_required: bool | None
    promo_source_url: str | None

    # --- fees / contract / device -----------------------------
    activation_fee_cad: float | None
    activation_fee_waived: bool | None
    activation_note: str | None
    contract_required: bool | None
    contract_length_months: int | None
    contract_note: str | None
    byod: bool | None
    byod_required: bool | None
    device_restrictions: str | None

    # --- data -------------------------------------------------
    data_base_gb: float | None
    data_bonus_gb: float | None
    data_promo_gb: float | None
    data_total_gb: float | None
    data_full_speed_gb: float | None
    data_unlimited: bool | None
    data_unlimited_is_full_speed: bool | None
    data_hard_cap: bool | None
    throttled_after_note: str | None
    throttle_speed: str | None
    overage_note: str | None
    overage_rate_per_gb_cad: float | None
    data_rollover: bool | None

    # --- network --------------------------------------------
    network_speed_tier: str | None
    network_technology: str | None
    max_download_mbps: float | None
    has_5g: bool | None

    # --- calling / travel ---------------------------------
    plan_type: str | None
    canada_wide_calling: bool | None
    unlimited_text: bool | None
    international_text: bool | None
    can_us_mex_note: str | None
    includes_us: bool | None
    includes_mexico: bool | None
    us_mex_data_gb: float | None
    international_roaming: bool | None
    international_roaming_note: str | None

    # --- features -----------------------------------------
    hotspot: bool | None
    hotspot_data_gb: float | None
    hotspot_note: str | None
    esim: bool | None
    wifi_calling: bool | None
    autopay_required: bool | None
    autopay_note: str | None

    # --- student -----------------------------------------
    student_plan: bool | None
    student_offer: bool | None
    student_eligibility_note: str | None

    # --- restricted eligibility -------------------------
    eligibility_restricted: bool | None
    eligibility_conditions: str | None

    # --- geography ---------------------------------------
    available_regions: list[str] | None
    geo_availability_note: str | None

    conditions: str | None
    availability: str | None
    attributes: dict

    # --- computed: current offer (serve time) -----------
    effective_price_cad: float | None = None
    is_current_offer: bool = False
    offer_active: bool = False
    offer_expired: bool = False
    offer_savings_cad: float | None = None
    offer_note: str | None = None

    # --- provenance / verification (computed + direct) --
    provider_name: str = ""
    source_mode: str = "official_automated"
    source_mode_label: str = ""
    verification_method: str = ""
    verified_by: str | None = None
    official_crosscheck: bool = False
    source_url: str = ""
    fetched_at: dt.datetime | None = None
    last_verified_at: dt.datetime | None = None
    first_verified_at: dt.datetime | None = None
    verification_status: str = ""          # effective
    stored_verification_status: str = ""
    confidence: float = 0.0
    is_rankable: bool = False              # effective
    freshness: str = "fresh"
    freshness_label: str = ""
    verification_event_count: int = 0

    issues: list[PlanIssueOut] = []


class MetaOut(BaseModel):
    municipality: str | None
    municipality_affects_results: bool
    generated_at: dt.datetime
    data_last_refreshed_at: dt.datetime | None
    data_oldest_verified_at: dt.datetime | None
    freshness: str | None
    freshness_label: str
    plan_count: int
    current_plan_count: int
    rankable_count: int
    current_offer_count: int
    flagged_count: int
    provider_count: int
    source_mode_counts: dict[str, int]
    providers: list[ProviderOut]
    notes: list[str]


class PlansResponse(BaseModel):
    meta: MetaOut
    plans: list[PlanOut]
    scores: list[dict]
    profiles: list[dict]


class OfferDetailOut(BaseModel):
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


class RankedPlanOut(BaseModel):
    rank: int
    plan_id: int
    provider_slug: str
    provider_name: str
    external_id: str
    plan_name: str | None

    # the full factual plan record (same shape as /api/plans) so the UI can
    # explain the ranking and disclose conditional pricing without a second call
    plan: PlanOut

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
    offer_detail: OfferDetailOut | None
    eligibility_note: str | None
    reasons: list[str]


class FiltersApplied(BaseModel):
    """Factual, normalized description of the V1 customization in effect for this
    request, so the frontend can explain what produced the list (or the empty
    state). No scoring logic — just the values that were used."""

    max_monthly_price_cad: float | None = None
    min_data_gb: float | None = None
    plan_type: str | None = None  # "prepaid" | "postpaid" | null
    require_5g: bool = False
    require_can_us_mex: bool = False
    require_international_roaming: bool = False
    student_eligible: bool = False
    autopay_willing: bool = False
    # true when at least one hard filter narrowed the candidate pool
    any_active: bool = False


class RankingResponse(BaseModel):
    preset: str
    municipality: str | None
    municipality_affects_results: bool
    student_eligible: bool
    autopay_willing: bool
    generated_at: dt.datetime
    candidate_count: int
    # candidates after verified/eligibility gating, before the custom hard filters
    pre_filter_candidate_count: int
    filters_applied: FiltersApplied
    results: list[RankedPlanOut]
