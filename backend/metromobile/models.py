"""Database schema.

Design notes
-----------
* Every normalized ``Plan`` links back to the ``RawDocument`` and ``Source`` it
  came from, so the UI can eventually show "where did this number come from".
* Factual fields that the source does not provide are stored as ``NULL`` -- never
  guessed. The open-ended ``attributes`` JSON column holds the untouched provider
  payload plus any provider-specific extras, so new attributes never need a
  migration.
* ``verification_status`` + ``last_verified_at`` drive the freshness policy; a
  plan that fails validation or goes stale is flagged, not silently shown.
* Types are portable: this runs on SQLite for local dev and on PostgreSQL
  unchanged (``JSON`` becomes ``jsonb`` there via a later migration if wanted).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# --- source modes -------------------------------------------------------
# official_automated : official carrier data fetched automatically
# official_manual    : official public data a person can view but bots cannot;
#                      imported via a controlled operator workflow with evidence
# trusted_secondary  : reputable third party; never "verified" on its own
OFFICIAL_AUTOMATED = "official_automated"
OFFICIAL_MANUAL = "official_manual"
TRUSTED_SECONDARY = "trusted_secondary"
SOURCE_MODES = (OFFICIAL_AUTOMATED, OFFICIAL_MANUAL, TRUSTED_SECONDARY)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Provider(Base):
    __tablename__ = "providers"

    slug: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    # Underlying radio network operator (matters for location-specific ranking later).
    network: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # "prepaid" | "postpaid" | "mixed" | None -- only set when the provider's whole
    # model is unambiguous and stated by the provider itself.
    plan_model: Mapped[str | None] = mapped_column(String(16), nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # the mode this provider's data currently comes in through
    default_source_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    sources: Mapped[list["Source"]] = relationship(back_populates="provider")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_slug: Mapped[str] = mapped_column(ForeignKey("providers.slug"), index=True)
    url: Mapped[str] = mapped_column(String(512))
    # one of models.SOURCE_MODES
    source_mode: Mapped[str] = mapped_column(
        String(24), default=OFFICIAL_AUTOMATED, server_default=OFFICIAL_AUTOMATED
    )
    # sub-type descriptor: "official_page" | "official_api" | "capture" | "secondary_page"
    kind: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    provider: Mapped[Provider] = relationship(back_populates="sources")

    __table_args__ = (UniqueConstraint("provider_slug", "url", name="uq_source_provider_url"),)


class RawDocument(Base):
    """An immutable record of one fetch or one manual capture. The bytes are
    written to ``raw_store/`` on disk; this row is the provenance index. Rows
    here are only ever inserted -- re-verifying a plan adds a new RawDocument,
    it never overwrites the evidence of what was previously observed."""

    __tablename__ = "raw_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 hex
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parser_version: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # "live" | "fixture" | "manual_import"
    retrieval: Mapped[str] = mapped_column(String(16), default="live")
    # manual-import provenance
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    captured_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    official_source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[Source] = relationship()


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        UniqueConstraint("provider_slug", "external_id", name="uq_plan_provider_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_slug: Mapped[str] = mapped_column(ForeignKey("providers.slug"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    raw_document_id: Mapped[int] = mapped_column(ForeignKey("raw_documents.id"))

    # --- identity -----------------------------------------------------------
    external_id: Mapped[str] = mapped_column(String(128))  # provider's own plan code
    plan_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    plan_local_name: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # --- pricing TIERS (unconditional vs autopay vs bundle vs promo) ----
    # regular_price_cad = the UNCONDITIONAL monthly price (no autopay/bundle/promo);
    # a discounted tier is only real for a customer who meets its conditions.
    price_period: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "monthly"|"annual"
    term_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regular_price_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    autopay_price_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    autopay_discount_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    autopay_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    bundle_price_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    bundle_discount_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    bundle_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    promo_price_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    promo_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    promo_stacks_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    pricing_notes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # simple display + legacy: the plan's standard monthly price (== regular_price_cad)
    monthly_price_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    price_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)

    # --- promotion / current offer (structured) -----------------------
    promo_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    promo_savings_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    promo_starts_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promo_ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promo_expiry_known: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    promo_duration_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    promo_new_customers_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    promo_online_only: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    promo_autopay_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    promo_source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # --- fees / contract / device -----------------------------------
    activation_fee_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    activation_fee_waived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    activation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    contract_length_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    byod: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    byod_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    device_restrictions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- data -----------------------------------------------------------
    data_base_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_bonus_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_promo_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_total_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_full_speed_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_unlimited: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    data_unlimited_is_full_speed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    data_hard_cap: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    throttled_after_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # free-text, network-dependent throttle policy (e.g. Freedom's full sentence),
    # not a single number -> Text, not a bounded String (PostgreSQL enforces the
    # length, SQLite does not).
    throttle_speed: Mapped[str | None] = mapped_column(Text, nullable=True)
    overage_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    overage_rate_per_gb_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    data_rollover: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- network / speed ---------------------------------------------
    network_speed_tier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    network_technology: Mapped[str | None] = mapped_column(String(16), nullable=True)
    max_download_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_5g: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- calling / messaging / travel ------------------------------
    plan_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # prepaid|postpaid
    canada_wide_calling: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unlimited_text: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    international_text: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    can_us_mex_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    includes_us: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    includes_mexico: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    us_mex_data_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    international_roaming: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    international_roaming_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- features -------------------------------------------------------
    hotspot: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    hotspot_data_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    hotspot_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    esim: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wifi_calling: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    autopay_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    autopay_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- student ------------------------------------------------------
    student_plan: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    student_offer: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    student_eligibility_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- restricted eligibility (partner / employer / exclusive offer) ---
    # True -> excluded from the default ranking unless the user is known to qualify.
    eligibility_restricted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    eligibility_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- geography (only when the source states a restriction) -------
    available_regions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    geo_availability_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # open-ended: raw provider payload + provider-specific extras
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- provenance / freshness ---------------------------------------
    # one of models.SOURCE_MODES
    source_mode: Mapped[str] = mapped_column(
        String(24), default=OFFICIAL_AUTOMATED, server_default=OFFICIAL_AUTOMATED
    )
    # "automated_fetch" | "operator_manual_review" | "secondary_fetch"
    #   | "secondary_manual" | "official_crosscheck"
    verification_method: Mapped[str] = mapped_column(
        String(32), default="automated_fetch", server_default="automated_fetch"
    )
    verified_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # a secondary-only record corroborated by an official record for the same plan
    official_crosscheck: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0"
    )
    source_url: Mapped[str] = mapped_column(String(512))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    # "verified" | "provisional" | "secondary_confirmed" | "stale" | "invalid"
    verification_status: Mapped[str] = mapped_column(String(24), default="verified")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    is_rankable: Mapped[bool] = mapped_column(Boolean, default=False)

    content_hash: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    issues: Mapped[list["PlanValidationIssue"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    verification_events: Mapped[list["PlanVerificationEvent"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
        order_by="PlanVerificationEvent.event_at",
    )


class PlanVerificationEvent(Base):
    """Append-only history of every time a plan was observed / verified. A
    re-verification adds a row here (pointing at its own immutable RawDocument)
    rather than overwriting what was seen before."""

    __tablename__ = "plan_verification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    provider_slug: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    event_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # "automated_refresh" | "manual_import" | "secondary_import" | "reverify"
    #   | "vanished" | "sweep_stale"
    event_kind: Mapped[str] = mapped_column(String(32))
    source_mode: Mapped[str] = mapped_column(String(24))
    verification_method: Mapped[str] = mapped_column(String(32))
    verification_status: Mapped[str] = mapped_column(String(24))
    confidence: Mapped[float] = mapped_column(Float)
    is_rankable: Mapped[bool] = mapped_column(Boolean)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_documents.id"), nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price_cad: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    plan: Mapped["Plan"] = relationship(back_populates="verification_events")


class PlanValidationIssue(Base):
    __tablename__ = "plan_validation_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plans.id"), nullable=True, index=True)
    refresh_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("refresh_runs.id"), nullable=True, index=True
    )
    provider_slug: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    field: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(16))  # "error" | "warning"
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    plan: Mapped["Plan | None"] = relationship(back_populates="issues")


class RefreshRun(Base):
    __tablename__ = "refresh_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_slug: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "success" | "partial" | "failed" | "source_unavailable"
    status: Mapped[str] = mapped_column(String(32), default="failed")
    source_mode: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_documents.id"), nullable=True
    )
    retrieval: Mapped[str | None] = mapped_column(String(16), nullable=True)
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    plans_upserted: Mapped[int] = mapped_column(Integer, default=0)
    plans_valid: Mapped[int] = mapped_column(Integer, default=0)
    plans_flagged: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
