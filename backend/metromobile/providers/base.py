"""Provider adapter contract.

Each carrier implements one :class:`ProviderAdapter`:

    fetch()  -> FetchResult          (raw bytes from the official source)
    parse(bytes) -> list[NormalizedPlan]

``parse`` MUST raise :class:`ParseError` if the source's structure no longer
matches what the parser expects, rather than silently emitting empty / wrong
plans. The pipeline turns that into a failed refresh run and leaves the last
good data in place.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

import httpx

from ..config import get_settings


class ParseError(RuntimeError):
    """The fetched document did not look the way the parser expects."""


class SourceUnavailable(RuntimeError):
    """The official source cannot be retrieved through a legitimate public path
    (anti-bot wall, no public structured data, etc.)."""


@dataclass
class FetchResult:
    content: bytes
    url: str
    http_status: int | None
    content_type: str | None
    fetched_at: dt.datetime
    retrieval: str  # "live" | "fixture" | "manual_import"


@dataclass
class NormalizedPlan:
    """One plan as extracted from a source.

    Every factual field the future ranking / profile / user-preference system will
    need has a home here. A field is only set when the official source actually
    states it -- otherwise it stays ``None`` (or ``[]`` -> ``None`` for lists).
    Nothing is inferred.
    """

    external_id: str
    plan_name: str | None = None
    plan_local_name: str | None = None

    # --- pricing TIERS (a discounted price is only real for a customer who
    #     meets its conditions; ranking must use the price the user is actually
    #     eligible for) ---------------------------------------------------------
    price_period: str | None = None           # "monthly" | "annual"
    term_months: int | None = None
    # the UNCONDITIONAL monthly price -- no AutoPay, no bundle, no promo. This is
    # the "universally available" price a default user is eligible for.
    regular_price_cad: float | None = None
    # price with ONLY AutoPay / pre-authorized payment met (near-universal)
    autopay_price_cad: float | None = None
    autopay_discount_cad: float | None = None
    autopay_conditions: str | None = None
    # price that requires a home-internet / streaming bundle or other
    # customer-specific condition -- NOT universally available
    bundle_price_cad: float | None = None
    bundle_discount_cad: float | None = None
    bundle_conditions: str | None = None
    # a time-limited promotional price (see the structured promo_* fields below)
    promo_price_cad: float | None = None
    promo_conditions: str | None = None
    promo_stacks_conditions: str | None = None  # does the promo price ALSO need autopay/bundle?
    # every raw "$X/mo" + its label seen on the card, verbatim, for review/provenance
    pricing_notes: list | None = None
    # kept for simple display + back-compat: the plan's standard monthly price
    # (== regular_price_cad when known). price_cad = same, legacy alias.
    monthly_price_cad: float | None = None
    price_cad: float | None = None

    # --- promotion / current offer (structured) --------------------------
    promo_name: str | None = None
    promo_savings_cad: float | None = None
    promo_starts_at: Optional[dt.datetime] = None
    promo_ends_at: Optional[dt.datetime] = None
    promo_expiry_known: bool | None = None    # True: real date; False: "limited time", no date; None: not mentioned
    promo_duration_months: int | None = None  # e.g. "$X/mo for the first 12 months"
    promo_new_customers_only: bool | None = None
    promo_online_only: bool | None = None
    promo_autopay_required: bool | None = None
    promo_source_url: str | None = None

    # --- fees / contract / device --------------------------------------
    activation_fee_cad: float | None = None
    activation_fee_waived: bool | None = None
    activation_note: str | None = None
    contract_required: bool | None = None
    contract_length_months: int | None = None
    contract_note: str | None = None
    byod: bool | None = None
    byod_required: bool | None = None
    device_restrictions: str | None = None

    # --- data ---------------------------------------------------------
    data_base_gb: float | None = None
    data_bonus_gb: float | None = None
    data_promo_gb: float | None = None
    data_total_gb: float | None = None          # total high-speed allowance
    data_full_speed_gb: float | None = None     # GB at full advertised speed before any throttle
    data_unlimited: bool | None = None          # any usable data past the cap (even if throttled)
    data_unlimited_is_full_speed: bool | None = None
    data_hard_cap: bool | None = None           # data stops entirely at the cap
    throttled_after_note: str | None = None
    throttle_speed: str | None = None
    overage_note: str | None = None
    overage_rate_per_gb_cad: float | None = None
    data_rollover: bool | None = None

    # --- network / speed --------------------------------------------
    network_speed_tier: str | None = None       # marketing string, e.g. "4G speeds up to 150Mbps"
    network_technology: str | None = None       # normalized: "5G+" | "5G" | "4G LTE" | "4G" | "3G"
    max_download_mbps: float | None = None
    has_5g: bool | None = None

    # --- calling / messaging / travel ------------------------------
    plan_type: str | None = None                # "prepaid" | "postpaid"
    canada_wide_calling: bool | None = None
    unlimited_text: bool | None = None
    international_text: bool | None = None
    can_us_mex_note: str | None = None
    includes_us: bool | None = None             # real US usage (calls/data), not just US texting
    includes_mexico: bool | None = None
    us_mex_data_gb: float | None = None
    international_roaming: bool | None = None
    international_roaming_note: str | None = None

    # --- features -------------------------------------------------
    hotspot: bool | None = None
    hotspot_data_gb: float | None = None
    hotspot_note: str | None = None
    esim: bool | None = None
    wifi_calling: bool | None = None
    autopay_required: bool | None = None
    autopay_note: str | None = None

    # --- student ------------------------------------------------
    student_plan: bool | None = None            # this plan is specifically a student plan
    student_offer: bool | None = None           # a student-specific discount/offer applies
    student_eligibility_note: str | None = None

    # --- restricted eligibility --------------------------------
    # True = this plan/price is NOT available to an ordinary customer (partner /
    # employer / exclusive / invite-only offer). The default Top-N ranking must
    # exclude it unless the user is known to qualify.
    eligibility_restricted: bool | None = None
    eligibility_conditions: str | None = None   # the verified condition to qualify

    # --- geography (only when the source states a restriction) ---
    available_regions: list[str] | None = None  # e.g. ["BC"], ["Canada"]; None = not stated
    geo_availability_note: str | None = None

    conditions: str | None = None
    availability: str | None = None

    attributes: dict = field(default_factory=dict)


@runtime_checkable
class ProviderAdapter(Protocol):
    slug: str
    display_name: str
    network: str | None
    plan_model: str | None
    homepage_url: str
    source_url: str
    # one of metromobile.models.SOURCE_MODES
    source_mode: str
    # "automated_fetch" | "operator_manual_review" | "secondary_fetch"
    verification_method: str
    source_kind: str  # "official_page" | "official_api" | "capture" | "secondary_page"
    source_description: str
    parser_version: str
    # True: parse() returns this provider's COMPLETE current catalogue, so a plan
    #   that disappears between fetches is genuinely gone -> mark invalid.
    # False: parse() returns a rotating sample (e.g. a "popular plans" widget);
    #   a plan simply not seen this run is left to age out via freshness, not flagged.
    catalog_is_complete: bool

    def fetch(self) -> FetchResult: ...
    def parse(self, content: bytes) -> list[NormalizedPlan]: ...


class HttpProviderAdapter:
    """Mixin providing a polite httpx GET + a fixture loader."""

    source_url: str
    source_kind: str
    parser_version: str

    def _get(self, url: str) -> FetchResult:
        settings = get_settings()
        headers = {"User-Agent": settings.http_user_agent, "Accept": "text/html,application/json"}
        resp = httpx.get(
            url,
            headers=headers,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
        )
        return FetchResult(
            content=resp.content,
            url=str(resp.url),
            http_status=resp.status_code,
            content_type=resp.headers.get("content-type"),
            fetched_at=dt.datetime.now(dt.timezone.utc),
            retrieval="live",
        )

    def load_fixture(self, path: str | Path) -> FetchResult:
        p = Path(path)
        return FetchResult(
            content=p.read_bytes(),
            url=self.source_url,
            http_status=None,
            content_type=None,
            fetched_at=dt.datetime.now(dt.timezone.utc),
            retrieval="fixture",
        )


class AutomatedAdapter(HttpProviderAdapter):
    """Base for carriers whose official data can be fetched automatically."""

    source_mode = "official_automated"
    verification_method = "automated_fetch"
    catalog_is_complete = True


class SecondaryAdapter(HttpProviderAdapter):
    """Base for reputable third-party sources fetched automatically. Records from
    these are confidence-capped and never rankable on their own -- see
    :mod:`metromobile.validation`. One adapter can emit plans for MANY providers."""

    source_mode = "trusted_secondary"
    verification_method = "secondary_fetch"
    catalog_is_complete = False  # aggregators surface a rotating subset


class ManualAdapter:
    """Base for carriers whose official public plans a person can view but which
    block automated retrieval. There is no ``fetch()``; an operator supplies a
    capture of the official page plus the transcribed plan fields, and the
    pipeline records both with full provenance.

    A subclass may override ``parse`` to extract plans from the capture itself;
    the default relies on the operator-supplied payload (validated against the
    normalized schema)."""

    source_mode = "official_manual"
    verification_method = "operator_manual_review"
    capture_format = "html"  # "html" | "text" | "json"
    catalog_is_complete = True

    def parse(self, capture: bytes, payload: list[dict]) -> list[NormalizedPlan]:
        raise NotImplementedError
