"""Refresh / import orchestrator.

    run_refresh(slug)         official_automated: fetch -> raw -> parse -> ... -> store
    run_manual_import(...)    official_manual / trusted_secondary: operator supplies a
                              capture + transcribed plans -> raw (immutable) -> ... -> store

One call == one ``RefreshRun`` row. Every plan write also appends a
``PlanVerificationEvent`` (append-only history), and every fetch/capture is kept
as an immutable ``RawDocument`` -- re-verifying never overwrites the evidence.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import BACKEND_DIR, get_settings
from .models import (
    OFFICIAL_AUTOMATED,
    OFFICIAL_MANUAL,
    TRUSTED_SECONDARY,
    Plan,
    PlanValidationIssue,
    PlanVerificationEvent,
    Provider,
    RawDocument,
    RefreshRun,
    Source,
)
from .providers import get_adapter
from .providers.base import FetchResult, NormalizedPlan, ParseError, SourceUnavailable
from .validation import validate_plan

RAW_STORE = BACKEND_DIR / "raw_store"

# every NormalizedPlan field except the open-ended attributes bag; kept in sync
# with the dataclass automatically so new schema fields flow straight through
_NORMALIZED_FIELDS = [f.name for f in dataclasses.fields(NormalizedPlan) if f.name != "attributes"]
_NORMALIZED_FIELD_SET = set(_NORMALIZED_FIELDS)


@dataclasses.dataclass
class RefreshOutcome:
    provider_slug: str
    status: str
    source_mode: str | None = None
    records_seen: int = 0
    plans_upserted: int = 0
    plans_valid: int = 0
    plans_flagged: int = 0
    error_message: str | None = None
    retrieval: str | None = None


def _plan_content_hash(norm: NormalizedPlan) -> str:
    payload = {k: getattr(norm, k) for k in _NORMALIZED_FIELDS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


_DATETIME_FIELDS = {"promo_starts_at", "promo_ends_at"}


def _coerce_iso(value):
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ParseError(f"cannot parse datetime {value!r}: {exc}") from exc
    return value


def normalized_from_dict(raw: dict) -> NormalizedPlan:
    """Build a NormalizedPlan from an operator-supplied plan dict. Unknown keys
    are preserved under ``attributes`` -- never dropped, never invented."""
    if not raw.get("external_id"):
        raise ParseError("manual plan record has no 'external_id'")
    known = {
        k: (_coerce_iso(v) if k in _DATETIME_FIELDS else v)
        for k, v in raw.items()
        if k in _NORMALIZED_FIELD_SET
    }
    extra = {k: v for k, v in raw.items() if k not in _NORMALIZED_FIELD_SET and k != "attributes"}
    attributes = dict(raw.get("attributes") or {})
    if extra:
        attributes["operator_supplied_extra"] = extra
    plan = NormalizedPlan(attributes=attributes, **known)
    # "current price" == the monthly figure when the operator only gave that
    if plan.price_cad is None and plan.monthly_price_cad is not None:
        plan.price_cad = plan.monthly_price_cad
    return plan


# ----------------------------------------------------------------------
_MODE_RANK = {"official_automated": 3, "official_manual": 2, "trusted_secondary": 1}


def _ensure_provider(session: Session, *, slug, display_name, network, plan_model,
                     homepage_url, source_mode) -> Provider:
    provider = session.get(Provider, slug)
    if provider is None:
        provider = Provider(slug=slug)
        session.add(provider)
    if display_name:
        provider.display_name = display_name
    if network is not None:
        provider.network = network
    if plan_model is not None:
        provider.plan_model = plan_model
    if homepage_url is not None:
        provider.homepage_url = homepage_url
    # keep the strongest source mode this provider has ever had (a secondary
    # refresh must not downgrade a provider that also has an official source)
    if provider.default_source_mode is None or (
        _MODE_RANK[source_mode] >= _MODE_RANK.get(provider.default_source_mode, 0)
    ):
        provider.default_source_mode = source_mode
    session.flush()
    return provider


def _ensure_source(session: Session, *, provider_slug, url, source_mode, kind, description) -> Source:
    source = session.scalar(
        select(Source).where(Source.provider_slug == provider_slug, Source.url == url)
    )
    if source is None:
        source = Source(provider_slug=provider_slug, url=url)
        session.add(source)
    source.source_mode = source_mode
    source.kind = kind
    source.description = description
    session.flush()
    return source


# capture file suffix -> the MIME type recorded on the RawDocument
_CAPTURE_CONTENT_TYPES = {
    "mhtml": "multipart/related",   # browser "Save Page As -> Web Page, Single File"
    "mht": "multipart/related",
    "html": "text/html",
    "htm": "text/html",
    "pdf": "application/pdf",
    "json": "application/json",
    "txt": "text/plain",
}


def capture_content_type(path: str | Path) -> str:
    return _CAPTURE_CONTENT_TYPES.get(
        Path(path).suffix.lower().lstrip("."), "application/octet-stream"
    )


def _store_raw(session: Session, *, provider_slug, source_id, content: bytes, content_type,
               http_status, parser_version, retrieval, fetched_at, operator=None,
               captured_at=None, official_source_url=None, ext: str | None = None) -> RawDocument:
    content_hash = hashlib.sha256(content).hexdigest()
    if ext is None:
        ext = "json" if (content_type or "").startswith("application/json") else "html"
    ts = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    folder = RAW_STORE / provider_slug
    folder.mkdir(parents=True, exist_ok=True)
    # identical bytes already on disk (from an earlier fetch) -> reuse that file;
    # the per-fetch record lives in the RawDocument row, not the filename.
    existing = next(iter(sorted(folder.glob(f"*-{content_hash[:12]}.{ext}"))), None)
    path = existing or (folder / f"{ts}-{content_hash[:12]}.{ext}")
    if not path.exists():
        path.write_bytes(content)
    raw = RawDocument(
        source_id=source_id, fetched_at=fetched_at, http_status=http_status,
        content_type=content_type, content_hash=content_hash, byte_size=len(content),
        parser_version=parser_version, storage_path=str(path.relative_to(BACKEND_DIR)),
        retrieval=retrieval, operator=operator, captured_at=captured_at,
        official_source_url=official_source_url,
    )
    session.add(raw)
    session.flush()
    return raw


def _store_plans(
    session: Session,
    *,
    run: RefreshRun,
    provider_slug: str,
    source: Source,
    raw: RawDocument,
    normalized: list[NormalizedPlan],
    source_mode: str,
    verification_method: str,
    source_url: str,
    verified_at: dt.datetime,
    now: dt.datetime,
    operator: str | None,
    event_kind: str,
    official_crosscheck: bool = False,
    catalog_is_complete: bool = True,
    event_note: str | None = None,
) -> tuple[int, int, int]:
    settings = get_settings()
    seen: set[str] = set()
    upserted = valid = flagged = 0

    for norm in normalized:
        if norm.external_id in seen:
            session.add(PlanValidationIssue(
                refresh_run_id=run.id, provider_slug=provider_slug, external_id=norm.external_id,
                severity="warning", field="external_id",
                message="duplicate plan in one import -- ignored",
            ))
            continue
        seen.add(norm.external_id)

        result = validate_plan(
            norm, provider_known=True, source_url=source_url, source_mode=source_mode,
            last_verified_at=verified_at, now=now, official_crosscheck=official_crosscheck,
            settings=settings,
        )

        plan = session.scalar(select(Plan).where(
            Plan.provider_slug == provider_slug, Plan.external_id == norm.external_id
        ))
        if plan is None:
            plan = Plan(provider_slug=provider_slug, external_id=norm.external_id, first_seen_at=now)
            session.add(plan)

        for f in _NORMALIZED_FIELDS:
            setattr(plan, f, getattr(norm, f))
        plan.source_id = source.id
        plan.raw_document_id = raw.id
        plan.attributes = norm.attributes
        plan.source_mode = source_mode
        plan.verification_method = verification_method
        plan.verified_by = operator
        plan.official_crosscheck = official_crosscheck
        # a per-plan source URL (e.g. an aggregator's detail page) wins over the
        # source-level URL
        plan.source_url = norm.attributes.get("_source_url") or source_url
        plan.fetched_at = raw.fetched_at
        plan.last_verified_at = verified_at
        plan.last_seen_at = now
        plan.verification_status = result.verification_status
        plan.confidence = result.confidence
        plan.is_rankable = result.is_rankable
        plan.content_hash = _plan_content_hash(norm)
        session.flush()

        for old in list(plan.issues):
            session.delete(old)
        for iss in result.issues:
            session.add(PlanValidationIssue(
                plan_id=plan.id, refresh_run_id=run.id, provider_slug=provider_slug,
                external_id=norm.external_id, field=iss.field, severity=iss.severity,
                message=iss.message,
            ))

        session.add(PlanVerificationEvent(
            plan_id=plan.id, provider_slug=provider_slug, external_id=norm.external_id,
            event_at=now, event_kind=event_kind, source_mode=source_mode,
            verification_method=verification_method, verification_status=result.verification_status,
            confidence=result.confidence, is_rankable=result.is_rankable, operator=operator,
            raw_document_id=raw.id, source_url=source_url, content_hash=plan.content_hash,
            price_cad=plan.price_cad if plan.price_cad is not None else plan.monthly_price_cad,
            note=event_note,
        ))

        upserted += 1
        valid += result.is_rankable
        flagged += not result.is_rankable

    # plans that disappeared from this provider's source (only meaningful when the
    # source returns the provider's COMPLETE catalogue)
    if not catalog_is_complete:
        return upserted, valid, flagged
    for plan in session.scalars(
        select(Plan).where(Plan.provider_slug == provider_slug, Plan.source_id == source.id)
    ).all():
        if plan.external_id not in seen:
            plan.is_rankable = False
            plan.verification_status = "invalid"
            plan.confidence = min(plan.confidence, 0.2)
            session.add(PlanValidationIssue(
                plan_id=plan.id, refresh_run_id=run.id, provider_slug=provider_slug,
                external_id=plan.external_id, field=None, severity="error",
                message="plan was not present in the latest fetch/import from the source",
            ))
            session.add(PlanVerificationEvent(
                plan_id=plan.id, provider_slug=provider_slug, external_id=plan.external_id,
                event_at=now, event_kind="vanished", source_mode=source_mode,
                verification_method=verification_method, verification_status="invalid",
                confidence=plan.confidence, is_rankable=False, operator=operator,
                source_url=source_url, note="not present in latest fetch/import",
            ))
            flagged += 1

    return upserted, valid, flagged


# ----------------------------------------------------------------------
def run_refresh(
    provider_slug: str,
    session: Session,
    *,
    fixture_path: str | Path | None = None,
) -> RefreshOutcome:
    """official_automated pipeline for one provider."""
    adapter = get_adapter(provider_slug)
    now = dt.datetime.now(dt.timezone.utc)
    source_mode = getattr(adapter, "source_mode", OFFICIAL_AUTOMATED)
    run = RefreshRun(
        provider_slug=provider_slug, started_at=now, source_url=adapter.source_url,
        source_mode=source_mode,
    )
    session.add(run)
    session.flush()

    _ensure_provider(
        session, slug=adapter.slug, display_name=adapter.display_name, network=adapter.network,
        plan_model=adapter.plan_model, homepage_url=adapter.homepage_url, source_mode=source_mode,
    )
    source = _ensure_source(
        session, provider_slug=adapter.slug, url=adapter.source_url, source_mode=source_mode,
        kind=adapter.source_kind, description=adapter.source_description,
    )

    try:
        fetch = adapter.load_fixture(fixture_path) if fixture_path else adapter.fetch()
    except SourceUnavailable as exc:
        run.status = "source_unavailable"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.error_message = str(exc)
        session.commit()
        return RefreshOutcome(provider_slug, "source_unavailable", source_mode, error_message=str(exc))

    run.http_status = fetch.http_status
    run.retrieval = fetch.retrieval
    if fetch.http_status is not None and fetch.http_status >= 400:
        run.status = "failed"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.error_message = f"HTTP {fetch.http_status} from {fetch.url}"
        session.commit()
        return RefreshOutcome(provider_slug, "failed", source_mode, error_message=run.error_message)

    raw = _store_raw(
        session, provider_slug=adapter.slug, source_id=source.id, content=fetch.content,
        content_type=fetch.content_type, http_status=fetch.http_status,
        parser_version=adapter.parser_version, retrieval=fetch.retrieval,
        fetched_at=fetch.fetched_at,
    )
    run.raw_document_id = raw.id

    try:
        normalized = adapter.parse(fetch.content)
    except ParseError as exc:
        run.status = "failed"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.error_message = f"parser: {exc}"
        session.add(PlanValidationIssue(
            refresh_run_id=run.id, provider_slug=provider_slug, severity="error",
            field=None, message=f"parse failed: {exc}",
        ))
        session.commit()
        return RefreshOutcome(provider_slug, "failed", source_mode, error_message=str(exc))

    run.records_seen = len(normalized)
    upserted, valid, flagged = _store_plans(
        session, run=run, provider_slug=adapter.slug, source=source, raw=raw,
        normalized=normalized, source_mode=source_mode,
        verification_method=getattr(adapter, "verification_method", "automated_fetch"),
        source_url=adapter.source_url, verified_at=now, now=now, operator=None,
        event_kind="automated_refresh",
        catalog_is_complete=getattr(adapter, "catalog_is_complete", True),
    )
    run.plans_upserted, run.plans_valid, run.plans_flagged = upserted, valid, flagged
    run.status = "success" if upserted else "partial"
    run.finished_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return RefreshOutcome(
        provider_slug, run.status, source_mode, records_seen=len(normalized),
        plans_upserted=upserted, plans_valid=valid, plans_flagged=flagged,
        retrieval=fetch.retrieval,
    )


def run_manual_import(
    session: Session,
    *,
    manifest: dict,
    capture_path: str | Path,
    operator: str,
    verified_at: dt.datetime | None = None,
    source_mode: str = OFFICIAL_MANUAL,
    official_crosscheck: bool = False,
    parser_version: str = "manual-import-v1",
    note: str | None = None,
    event_kind: str | None = None,
) -> RefreshOutcome:
    """official_manual / trusted_secondary import.

    ``manifest`` is a dict:
        {
          "provider": {"slug", "display_name", "network", "plan_model", "homepage_url"},
          "source":   {"url", "kind"},
          "plans":    [ {normalized plan fields...}, ... ]
        }
    ``capture_path`` is the operator's saved copy of the official page (kept as
    immutable evidence).
    """
    now = dt.datetime.now(dt.timezone.utc)
    verified_at = verified_at or now
    if source_mode not in (OFFICIAL_MANUAL, TRUSTED_SECONDARY):
        raise ValueError(f"manual import mode must be official_manual or trusted_secondary, got {source_mode!r}")

    pinfo = manifest.get("provider") or {}
    sinfo = manifest.get("source") or {}
    slug = pinfo.get("slug")
    source_url = sinfo.get("url")
    if not slug or not source_url:
        raise ValueError("manifest needs provider.slug and source.url")
    plans_raw = manifest.get("plans") or []

    verification_method = (
        "secondary_manual" if source_mode == TRUSTED_SECONDARY else "operator_manual_review"
    )
    kind = sinfo.get("kind") or ("secondary_page" if source_mode == TRUSTED_SECONDARY else "capture")

    run = RefreshRun(
        provider_slug=slug, started_at=now, source_url=source_url,
        source_mode=source_mode, operator=operator,
    )
    session.add(run)
    session.flush()

    _ensure_provider(
        session, slug=slug, display_name=pinfo.get("display_name"),
        network=pinfo.get("network"), plan_model=pinfo.get("plan_model"),
        homepage_url=pinfo.get("homepage_url"), source_mode=source_mode,
    )
    source = _ensure_source(
        session, provider_slug=slug, url=source_url, source_mode=source_mode, kind=kind,
        description=sinfo.get("description") or f"{source_mode} import by operator",
    )

    content = Path(capture_path).read_bytes()
    ctype = capture_content_type(capture_path)  # .mhtml -> multipart/related, .html -> text/html, ...
    capture_ext = Path(capture_path).suffix.lower().lstrip(".") or "bin"
    raw = _store_raw(
        session, provider_slug=slug, source_id=source.id, content=content, content_type=ctype,
        http_status=None, parser_version=parser_version, retrieval="manual_import",
        fetched_at=verified_at, operator=operator, captured_at=verified_at,
        official_source_url=source_url, ext=capture_ext,
    )
    raw.notes = f"operator capture: {Path(capture_path).name} ({ctype})"
    run.raw_document_id = raw.id
    run.retrieval = "manual_import"

    try:
        normalized = [normalized_from_dict(p) for p in plans_raw]
    except ParseError as exc:
        run.status = "failed"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.error_message = f"manifest: {exc}"
        session.commit()
        return RefreshOutcome(slug, "failed", source_mode, error_message=str(exc))

    run.records_seen = len(normalized)
    default_kind = "secondary_import" if source_mode == TRUSTED_SECONDARY else "manual_import"
    upserted, valid, flagged = _store_plans(
        session, run=run, provider_slug=slug, source=source, raw=raw, normalized=normalized,
        source_mode=source_mode, verification_method=verification_method, source_url=source_url,
        verified_at=verified_at, now=now, operator=operator,
        event_kind=event_kind or default_kind,
        official_crosscheck=official_crosscheck, event_note=note,
    )
    run.plans_upserted, run.plans_valid, run.plans_flagged = upserted, valid, flagged
    run.status = "success" if upserted else "partial"
    run.finished_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return RefreshOutcome(
        slug, run.status, source_mode, records_seen=len(normalized),
        plans_upserted=upserted, plans_valid=valid, plans_flagged=flagged, retrieval="manual_import",
    )


def run_secondary_refresh(adapter_slug: str, session: Session, *, fixture_path=None) -> RefreshOutcome:
    """trusted_secondary pipeline. One aggregator adapter fetches once and emits
    plans for MANY carriers; each plan dict carries
    ``attributes["_provider"] = {slug, display_name, network, plan_model}`` and
    ``attributes["_source_url"]`` (the aggregator's page for that plan)."""
    adapter = get_adapter(adapter_slug)
    now = dt.datetime.now(dt.timezone.utc)
    source_mode = TRUSTED_SECONDARY
    run = RefreshRun(
        provider_slug=adapter_slug, started_at=now, source_url=adapter.source_url,
        source_mode=source_mode,
    )
    session.add(run)
    session.flush()

    try:
        fetch = adapter.load_fixture(fixture_path) if fixture_path else adapter.fetch()
    except SourceUnavailable as exc:
        run.status = "source_unavailable"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.error_message = str(exc)
        session.commit()
        return RefreshOutcome(adapter_slug, "source_unavailable", source_mode, error_message=str(exc))

    run.http_status = fetch.http_status
    run.retrieval = fetch.retrieval
    if fetch.http_status is not None and fetch.http_status >= 400:
        run.status = "failed"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.error_message = f"HTTP {fetch.http_status} from {fetch.url}"
        session.commit()
        return RefreshOutcome(adapter_slug, "failed", source_mode, error_message=run.error_message)

    try:
        normalized = adapter.parse(fetch.content)
    except ParseError as exc:
        run.status = "failed"
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.error_message = f"parser: {exc}"
        session.add(PlanValidationIssue(
            refresh_run_id=run.id, provider_slug=adapter_slug, severity="error",
            field=None, message=f"parse failed: {exc}",
        ))
        session.commit()
        return RefreshOutcome(adapter_slug, "failed", source_mode, error_message=str(exc))

    run.records_seen = len(normalized)

    # group by carrier
    groups: dict[str, list[NormalizedPlan]] = {}
    for np in normalized:
        pslug = (np.attributes.get("_provider") or {}).get("slug")
        if not pslug_valid(pslug):
            session.add(PlanValidationIssue(
                refresh_run_id=run.id, provider_slug=adapter_slug, severity="warning",
                field="_provider", message=f"secondary plan without a provider slug: {np.external_id}",
            ))
            continue
        groups.setdefault(pslug, []).append(np)

    total_up = total_valid = total_flag = 0
    first_raw_id = None
    for pslug, plans in groups.items():
        pmeta = plans[0].attributes.get("_provider") or {}
        _ensure_provider(
            session, slug=pslug, display_name=pmeta.get("display_name"),
            network=pmeta.get("network"), plan_model=pmeta.get("plan_model"),
            homepage_url=pmeta.get("homepage_url"), source_mode=source_mode,
        )
        source = _ensure_source(
            session, provider_slug=pslug, url=adapter.source_url, source_mode=source_mode,
            kind="secondary_page", description=adapter.source_description,
        )
        raw = _store_raw(
            session, provider_slug=pslug, source_id=source.id, content=fetch.content,
            content_type=fetch.content_type, http_status=fetch.http_status,
            parser_version=adapter.parser_version, retrieval=fetch.retrieval,
            fetched_at=fetch.fetched_at,
        )
        first_raw_id = first_raw_id or raw.id
        for np in plans:
            np.attributes.setdefault("_aggregator", adapter.display_name)
        up, val, flag = _store_plans(
            session, run=run, provider_slug=pslug, source=source, raw=raw, normalized=plans,
            source_mode=source_mode, verification_method=adapter.verification_method,
            source_url=plans[0].attributes.get("_source_url") or adapter.source_url,
            verified_at=now, now=now, operator=None, event_kind="secondary_import",
            catalog_is_complete=False,
        )
        total_up += up
        total_valid += val
        total_flag += flag

    run.raw_document_id = first_raw_id
    run.plans_upserted, run.plans_valid, run.plans_flagged = total_up, total_valid, total_flag
    run.status = "success" if total_up else "partial"
    run.finished_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return RefreshOutcome(
        adapter_slug, run.status, source_mode, records_seen=len(normalized),
        plans_upserted=total_up, plans_valid=total_valid, plans_flagged=total_flag,
        retrieval=fetch.retrieval,
    )


def pslug_valid(s) -> bool:
    return bool(s) and isinstance(s, str)


def sweep_stale(session: Session, *, now: dt.datetime | None = None) -> list[tuple[str, str]]:
    """Persist freshness transitions: any plan whose last verification is now
    older than its mode's re-verify window becomes ``stale`` and loses ranking
    eligibility. Returns the (provider_slug, external_id) pairs that changed."""
    from .freshness import STALE, freshness_state

    now = now or dt.datetime.now(dt.timezone.utc)
    settings = get_settings()
    changed: list[tuple[str, str]] = []
    for plan in session.scalars(select(Plan)).all():
        if plan.verification_status in ("invalid", "stale"):
            continue
        state = freshness_state(plan.last_verified_at, source_mode=plan.source_mode, now=now, settings=settings)
        if state == STALE:
            plan.verification_status = "stale"
            plan.is_rankable = False
            plan.confidence = round(plan.confidence * 0.5, 2)
            session.add(PlanVerificationEvent(
                plan_id=plan.id, provider_slug=plan.provider_slug, external_id=plan.external_id,
                event_at=now, event_kind="sweep_stale", source_mode=plan.source_mode,
                verification_method=plan.verification_method, verification_status="stale",
                confidence=plan.confidence, is_rankable=False, operator=None,
                source_url=plan.source_url,
                note="exceeded re-verification window for its source mode",
            ))
            changed.append((plan.provider_slug, plan.external_id))
    session.commit()
    return changed
