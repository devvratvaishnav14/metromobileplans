"""``metromobile`` command-line interface.

    metromobile init-db                     create tables (local dev)

    # official_automated
    metromobile refresh chatr                fetch + normalize + store one carrier
    metromobile refresh chatr --fixture fixtures/chatr/plans_page.html

    # official_manual: draft from a saved capture, review, then import
    metromobile draft-manifest bell --capture imports/bell/captures/2026-09-06.mhtml
    metromobile import --manifest m.plans.jsonc --capture page.mhtml --operator NAME
    metromobile reverify --manifest m.plans.jsonc --capture page.mhtml --operator NAME

    metromobile sweep                        expire stale manual/secondary data
    metromobile providers                    list providers + source mode + freshness
    metromobile plans                        show stored plans
    metromobile provenance <plan-id>         show a plan's verification history
    metromobile runs                         recent refresh/import runs
    metromobile serve                        run the API (uvicorn)
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from .config import BACKEND_DIR, get_settings
from .db import Base, SessionLocal, engine
from .drafting import DraftError, build_draft_manifest
from .models import Plan, Provider, RawDocument, RefreshRun
from .pipeline import (
    capture_content_type,
    run_manual_import,
    run_refresh,
    run_secondary_refresh,
    sweep_stale,
)
from .providers import IMPLEMENTED, REGISTRY, SECONDARY

app = typer.Typer(add_completion=False, help="metro-mobile-plans data pipeline + API")
console = Console()


@app.command("init-db")
def init_db() -> None:
    """Create all tables in the configured database (SQLite dev; use Alembic for PostgreSQL)."""
    Base.metadata.create_all(engine)
    console.print(f"[green]tables created[/] in {get_settings().database_url}")


_V1_DATASET = BACKEND_DIR / "fixtures" / "ranking" / "v1_dataset.json"
_MANUAL_EVIDENCE = BACKEND_DIR / "fixtures" / "manual_example" / "capture.html"
_CHATR_SNAPSHOT = BACKEND_DIR / "fixtures" / "chatr" / "plans_page.html"
# the real dates the operator verified each source; kept for honest provenance
_V1_VERIFIED_AT = dt.datetime(2026, 9, 9, 12, 0, tzinfo=dt.timezone.utc)
_V1_MANUAL_PROVIDERS = ("bell", "koodo", "freedom-mobile")

# the frozen, approved V1 official dataset — a fresh database must reproduce this
_EXPECTED_VERIFIED = 26
_EXPECTED_RANKABLE = 24


@app.command()
def bootstrap(
    force: bool = typer.Option(
        False, help="re-run the imports even if plans already exist (idempotent upserts)"
    ),
    live_chatr: bool = typer.Option(
        False, help="fetch Chatr live instead of from the reviewed snapshot"
    ),
) -> None:
    """One-time production bootstrap: reproduce the approved V1 official dataset
    on a fresh database through the normal verified import pipeline.

    Bell / Koodo / Freedom  -> official_manual import of the reviewed V1 dataset
    Chatr                    -> official_automated refresh (reviewed snapshot by
                                default; the scheduled job keeps it live after)

    Safe to re-run: every write upserts on (provider, external_id). Never drops
    or resets anything. Exits non-zero if the resulting counts don't match the
    frozen expectation, so a bad deploy fails loudly instead of drifting.
    """
    if not _V1_DATASET.exists():
        console.print(f"[red]missing {_V1_DATASET}[/] — cannot bootstrap")
        raise typer.Exit(1)

    with SessionLocal() as session:
        existing = session.scalar(select(func.count(Plan.id))) or 0
        if existing and not force:
            console.print(
                f"[yellow]database already has {existing} plan(s)[/] — skipping bootstrap "
                "(pass --force to re-run the idempotent imports)."
            )
            _report_official_counts(session)
            raise typer.Exit(0)

        dataset = json.loads(_V1_DATASET.read_text())

        for slug in _V1_MANUAL_PROVIDERS:
            block = dataset[slug]
            manifest = {
                "provider": block["provider"],
                "source": block["source"],
                "plans": block["plans"],
            }
            outcome = run_manual_import(
                session,
                manifest=manifest,
                capture_path=_MANUAL_EVIDENCE,
                operator="V1 approved snapshot (2026-09-09)",
                verified_at=_V1_VERIFIED_AT,
                source_mode="official_manual",
                note="production bootstrap from the reviewed V1 dataset",
            )
            _print_outcome(slug, outcome)
            if outcome.status not in ("success", "partial"):
                raise typer.Exit(1)

        chatr_fixture = None if live_chatr else _CHATR_SNAPSHOT
        chatr_outcome = run_refresh("chatr", session, fixture_path=chatr_fixture)
        _print_outcome("chatr", chatr_outcome)
        if chatr_outcome.status not in ("success", "partial"):
            raise typer.Exit(1)

        verified, rankable = _report_official_counts(session)

    if not live_chatr and (verified != _EXPECTED_VERIFIED or rankable != _EXPECTED_RANKABLE):
        console.print(
            f"[red]count drift[/]: expected {_EXPECTED_VERIFIED} verified / "
            f"{_EXPECTED_RANKABLE} rankable official plans, got {verified} / {rankable}. "
            "Investigate before serving."
        )
        raise typer.Exit(1)
    console.print("[green]bootstrap complete[/] — approved V1 dataset in place.")


def _report_official_counts(session) -> tuple[int, int]:
    rows = session.scalars(
        select(Plan).where(Plan.source_mode != "trusted_secondary")
    ).all()
    verified = sum(1 for p in rows if p.verification_status == "verified")
    rankable = sum(1 for p in rows if p.is_rankable)
    restricted = sum(1 for p in rows if p.eligibility_restricted)
    by_provider: dict[str, int] = {}
    for p in rows:
        by_provider[p.provider_slug] = by_provider.get(p.provider_slug, 0) + 1
    console.print(
        f"[bold]official plans:[/] {len(rows)} total · {verified} verified · "
        f"{rankable} rankable · {restricted} eligibility-gated  "
        f"({', '.join(f'{k}={v}' for k, v in sorted(by_provider.items()))})"
    )
    return verified, rankable


@app.command()
def refresh(
    provider: str = typer.Argument(..., help=f"one of: {', '.join(sorted(REGISTRY))}"),
    fixture: Path | None = typer.Option(None, help="parse this saved file instead of fetching"),
) -> None:
    """Fetch a source -> parse -> normalize -> validate -> store.

    official_automated adapters fetch one carrier; trusted_secondary adapters
    (e.g. `whistleout`) fetch an aggregator and emit plans for several carriers."""
    if provider not in REGISTRY:
        raise typer.BadParameter(f"unknown provider {provider!r}")
    if provider not in IMPLEMENTED and fixture is None:
        console.print(f"[yellow]{provider} has no automated source wired -- use `metromobile import`.[/]")
    with SessionLocal() as session:
        if provider in SECONDARY:
            outcome = run_secondary_refresh(provider, session, fixture_path=fixture)
        else:
            outcome = run_refresh(provider, session, fixture_path=fixture)
    _print_outcome(provider, outcome)
    raise typer.Exit(0 if outcome.status in ("success", "partial") else 1)


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments that are NOT inside a JSON string. A trailing
    comma before ] or } is also tolerated."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
        elif c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        else:
            out.append(c)
        i += 1
    cleaned = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", cleaned)


def _load_manifest(path: Path) -> dict:
    """Accepts .json or .jsonc (// and /* */ comments + trailing commas)."""
    if not path.exists():
        raise typer.BadParameter(f"manifest not found: {path}")
    try:
        return json.loads(_strip_jsonc(path.read_text()))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{path} is not valid JSON: {exc}") from exc


def _require_reviewed(data: dict, path: Path) -> None:
    """A file produced by `draft-manifest` must be checked by a human first."""
    draft = data.get("_draft")
    if isinstance(draft, dict) and draft.get("reviewed") is not True:
        raise typer.BadParameter(
            f"{path} is an unreviewed auto-draft.\n"
            "  Check every plan and value against the official page, then either\n"
            '  set  "_draft": { ..., "reviewed": true }  or delete the _draft block,\n'
            "  and re-run."
        )


_DRAFT_HEADER = """\
// ============================================================================
//  AUTO-EXTRACTED DRAFT MANIFEST -- NOT YET VERIFIED
//
//  Generated by `metromobile draft-manifest` from your saved official capture.
//  The capture is the factual source. Every value below was pattern-matched and
//  may be wrong; fields the tool wasn't sure about are null.
//
//  Before importing:
//   1. Open the official page (or the .mhtml) and check every plan + every field.
//   2. Fix anything wrong. Fill nulls where the page clearly states a value.
//      Each plan's "_review" block lists what was auto-filled and what to check.
//   3. Set  "_draft": { "reviewed": true }   (or delete the whole _draft block).
//
//  `metromobile import` will REFUSE this file until step 3 is done.
//  You remain the manual verifier: the import records YOU as the operator.
// ============================================================================
"""


def _dump_jsonc(manifest: dict, path: Path) -> None:
    path.write_text(_DRAFT_HEADER + "\n" + json.dumps(manifest, indent=2) + "\n")


@app.command("draft-manifest")
def draft_manifest_cmd(
    provider: str = typer.Argument(..., help="only 'bell' for now"),
    capture: Path = typer.Option(
        ..., help="primary saved official page (.mhtml / .html). For Bell: the "
        "'Mobility only' tab -- the unconditional pricing."
    ),
    with_streaming: Path | None = typer.Option(
        None, "--with-streaming",
        help="Bell only: a second capture of the 'With Streaming' tab. Its bundle "
        "prices are recorded as bundle_price_cad; the unconditional price still "
        "comes from the primary capture.",
    ),
    out: Path | None = typer.Option(None, help="output path (default: <capture>.plans.jsonc)"),
    force: bool = typer.Option(False, help="overwrite an existing draft file"),
) -> None:
    """Pre-fill a draft import manifest from a saved official capture.

    Extracts every plan + field it can confidently read; leaves the rest null;
    marks the file unreviewed. It does NOT touch the database -- you review it,
    then run `metromobile import` yourself."""
    _check_capture(capture)
    if with_streaming is not None:
        _check_capture(with_streaming)
    target = out or capture.with_suffix("").with_suffix(".plans.jsonc")
    if target.exists() and not force:
        raise typer.BadParameter(f"{target} already exists -- pass --force to overwrite")

    try:
        manifest = build_draft_manifest(
            provider, capture, streaming_capture_path=with_streaming
        )
    except DraftError as exc:
        console.print(f"[red]could not auto-extract:[/] {exc}")
        template = Path(f"imports/{provider}/manifest.template.jsonc")
        if template.exists():
            console.print(
                f"[yellow]falling back to the blank template.[/] "
                f"Copy it and fill it in manually:\n  cp {template} {target}"
            )
        raise typer.Exit(2) from None

    _dump_jsonc(manifest, target)
    n = manifest["_draft"]["plan_count"]
    console.print(f"[green]wrote {target}[/]  ({n} draft plan{'s' if n != 1 else ''})")
    console.print(
        f"[dim]next: open it, verify every value against the {provider} page, set "
        '"_draft":{"reviewed":true}, then `metromobile import`.[/]'
    )


def _parse_when(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def _check_capture(capture: Path) -> None:
    if not capture.exists():
        raise typer.BadParameter(f"capture not found: {capture}")
    size = capture.stat().st_size
    ctype = capture_content_type(capture)
    console.print(
        f"[dim]capture: {capture.name} · {ctype} · {size:,} bytes[/]"
    )
    if ctype == "application/octet-stream":
        console.print(
            "[yellow]note: unrecognized capture extension — stored as-is. "
            ".mhtml / .html / .pdf are the expected formats.[/]"
        )
    if size < 2000:
        console.print("[yellow]warning: capture is very small — did the page save correctly?[/]")


@app.command("import")
def import_manual(
    manifest: Path = typer.Option(..., help=".json/.jsonc: {provider, source, plans[]}"),
    capture: Path = typer.Option(
        ..., help="operator's saved official page (evidence): .mhtml / .html / .pdf"
    ),
    operator: str = typer.Option(..., help="who performed the verification"),
    mode: str = typer.Option("official_manual", help="official_manual | trusted_secondary"),
    verified_at: str | None = typer.Option(
        None, help="ISO-8601, e.g. 2026-09-06T14:00:00Z. Omit -> the moment you run this."
    ),
    note: str | None = typer.Option(None, help="free-text note kept in the verification history"),
    crosscheck: bool = typer.Option(False, help="(secondary) an official record corroborates this"),
) -> None:
    """official_manual / trusted_secondary: import operator-verified plans with evidence.

    The capture file is kept verbatim as provenance -- an .mhtml is recorded as
    multipart/related, not disguised as HTML. Omit --verified-at for a fresh
    capture; pass it only when importing an older one."""
    if mode not in ("official_manual", "trusted_secondary"):
        raise typer.BadParameter("mode must be official_manual or trusted_secondary")
    _check_capture(capture)
    data = _load_manifest(manifest)
    _require_reviewed(data, manifest)
    with SessionLocal() as session:
        outcome = run_manual_import(
            session, manifest=data, capture_path=capture, operator=operator,
            verified_at=_parse_when(verified_at), source_mode=mode,
            official_crosscheck=crosscheck, note=note,
        )
    _print_outcome(outcome.provider_slug, outcome)
    raise typer.Exit(0 if outcome.status in ("success", "partial") else 1)


@app.command()
def reverify(
    manifest: Path = typer.Option(..., help="a NEWER capture's manifest for a provider already imported"),
    capture: Path = typer.Option(..., help="the newer saved page: .mhtml / .html / .pdf"),
    operator: str = typer.Option(...),
    verified_at: str | None = typer.Option(
        None, help="ISO-8601. Omit -> the moment you run this."
    ),
    note: str | None = typer.Option(None),
) -> None:
    """Re-verify an already-imported official_manual carrier from a fresh capture.

    Shows a per-plan field diff, then appends the new capture + history WITHOUT
    deleting the previous evidence or observations."""
    _check_capture(capture)
    data = _load_manifest(manifest)
    _require_reviewed(data, manifest)
    slug = (data.get("provider") or {}).get("slug")
    if not slug:
        raise typer.BadParameter("manifest has no provider.slug")

    with SessionLocal() as session:
        existing = {
            p.external_id: p
            for p in session.scalars(select(Plan).where(Plan.provider_slug == slug)).all()
        }
        if not existing:
            raise typer.BadParameter(
                f"{slug} has no imported plans yet -- use `metromobile import` for the first import"
            )

        _print_reverify_diff(existing, data.get("plans") or [])

        outcome = run_manual_import(
            session, manifest=data, capture_path=capture, operator=operator,
            verified_at=_parse_when(verified_at), source_mode="official_manual",
            note=note or "re-verification", event_kind="reverify",
        )
    _print_outcome(slug, outcome)
    console.print("[dim]previous captures and history are retained -- see `metromobile provenance <id>`[/]")
    raise typer.Exit(0 if outcome.status in ("success", "partial") else 1)


_DIFF_FIELDS = [
    "monthly_price_cad", "regular_price_cad", "promo_price_cad", "promo_ends_at",
    "data_total_gb", "data_bonus_gb", "data_promo_gb", "data_unlimited",
    "plan_type", "network_technology", "has_5g", "contract_required", "availability",
]


def _norm(v: object) -> object:
    if v is None:
        return None
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return str(v)


def _print_reverify_diff(existing: dict, new_plans: list[dict]) -> None:
    table = Table(title="what changes on re-verify")
    for c in ("plan", "field", "was", "now"):
        table.add_column(c)
    rows = 0
    new_ids = set()
    for np in new_plans:
        ext = str(np.get("external_id"))
        new_ids.add(ext)
        cur = existing.get(ext)
        if cur is None:
            table.add_row(ext[:28], "(new plan)", "—", "—")
            rows += 1
            continue
        for f in _DIFF_FIELDS:
            old_v, new_v = _norm(getattr(cur, f, None)), _norm(np.get(f))
            if old_v != new_v:
                table.add_row(ext[:28], f, str(old_v), str(new_v))
                rows += 1
    for ext in existing:
        if ext not in new_ids:
            table.add_row(ext[:28], "(gone from source)", "present", "absent → invalid")
            rows += 1
    console.print(table if rows else "[green]no field changes vs the stored data[/]")


@app.command()
def sweep() -> None:
    """Expire data past its re-verification window: mark stale + drop ranking eligibility."""
    with SessionLocal() as session:
        changed = sweep_stale(session)
    if not changed:
        console.print("[green]nothing went stale[/]")
    else:
        console.print(f"[yellow]{len(changed)} plan(s) marked stale:[/]")
        for slug, ext in changed:
            console.print(f"  {slug} / {ext}")


@app.command()
def providers() -> None:
    """List providers, their source mode, and overall freshness."""
    from .freshness import freshness_state

    now = dt.datetime.now(dt.timezone.utc)
    with SessionLocal() as session:
        table = Table()
        for c in ("provider", "network", "mode", "plans", "rankable", "oldest verified"):
            table.add_column(c)
        for pr in session.scalars(select(Provider).order_by(Provider.slug)).all():
            plans = session.scalars(select(Plan).where(Plan.provider_slug == pr.slug)).all()
            oldest = min((p.last_verified_at for p in plans), default=None)
            fresh = (
                freshness_state(oldest, source_mode=pr.default_source_mode or "official_automated", now=now)
                if oldest else "—"
            )
            table.add_row(
                pr.slug, pr.network or "—", pr.default_source_mode or "—",
                str(len(plans)), str(sum(1 for p in plans if p.is_rankable)), fresh,
            )
        console.print(table)


@app.command()
def plans(provider: str | None = typer.Option(None)) -> None:
    """Print the plans currently stored."""
    with SessionLocal() as session:
        stmt = select(Plan).order_by(Plan.provider_slug, Plan.monthly_price_cad)
        if provider:
            stmt = stmt.where(Plan.provider_slug == provider)
        rows = session.scalars(stmt).all()
        table = Table(show_lines=False)
        for col in ("provider", "plan", "price", "data", "type", "mode", "status", "rankable"):
            table.add_column(col)
        for p in rows:
            price = (
                f"${p.monthly_price_cad}/mo" if p.monthly_price_cad is not None
                else (f"${p.price_cad}/{p.price_period or '?'}" if p.price_cad is not None else "—")
            )
            data = "unlimited" if p.data_unlimited else (
                str(p.data_total_gb) if p.data_total_gb is not None else "—"
            )
            table.add_row(
                p.provider_slug, (p.plan_name or "")[:40], price, data, p.plan_type or "—",
                p.source_mode.replace("official_", "").replace("trusted_", ""),
                p.verification_status, "yes" if p.is_rankable else "no",
            )
        console.print(table)
        console.print(f"[dim]{len(rows)} plan(s)[/]")


@app.command()
def provenance(plan_id: int) -> None:
    """Show a plan's immutable verification history."""
    with SessionLocal() as session:
        plan = session.get(Plan, plan_id)
        if plan is None:
            raise typer.BadParameter(f"no plan with id {plan_id}")
        console.print(
            f"[bold]{plan.provider_slug} / {plan.external_id}[/] — {plan.plan_name}\n"
            f"mode={plan.source_mode}  method={plan.verification_method}  "
            f"verified_by={plan.verified_by or '—'}  status={plan.verification_status}"
        )
        table = Table()
        for c in ("when", "event", "status", "rankable", "price", "operator", "raw doc", "hash"):
            table.add_column(c)
        for e in sorted(plan.verification_events, key=lambda x: x.event_at):
            raw = session.get(RawDocument, e.raw_document_id) if e.raw_document_id else None
            table.add_row(
                e.event_at.strftime("%Y-%m-%d %H:%M"), e.event_kind, e.verification_status,
                "yes" if e.is_rankable else "no",
                f"${e.price_cad}" if e.price_cad is not None else "—",
                e.operator or "—",
                (raw.storage_path.split("/")[-1] if raw and raw.storage_path else "—"),
                (e.content_hash or "")[:12],
            )
        console.print(table)


@app.command()
def runs(limit: int = 10) -> None:
    """Show recent refresh / import runs."""
    with SessionLocal() as session:
        rows = session.scalars(
            select(RefreshRun).order_by(RefreshRun.started_at.desc()).limit(limit)
        ).all()
        table = Table()
        for col in ("id", "provider", "mode", "started", "status", "seen", "rankable", "flagged", "note"):
            table.add_column(col)
        for r in rows:
            table.add_row(
                str(r.id), r.provider_slug, (r.source_mode or "—").replace("official_", ""),
                r.started_at.strftime("%m-%d %H:%M"), r.status, str(r.records_seen),
                str(r.plans_valid), str(r.plans_flagged), (r.error_message or "")[:48],
            )
        console.print(table)


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Run the API with uvicorn."""
    import uvicorn

    uvicorn.run("metromobile.api:app", host=host, port=port, reload=reload)


def _print_outcome(provider: str, outcome) -> None:
    color = {"success": "green", "partial": "yellow"}.get(outcome.status, "red")
    console.print(
        f"[{color}]{provider}: {outcome.status}[/]  "
        f"({outcome.source_mode or '?'} / {outcome.retrieval or 'n/a'})"
    )
    if outcome.error_message:
        console.print(f"  [red]{outcome.error_message}[/]")
    else:
        console.print(
            f"  records seen: {outcome.records_seen}  upserted: {outcome.plans_upserted}  "
            f"rankable: {outcome.plans_valid}  flagged: {outcome.plans_flagged}"
        )


if __name__ == "__main__":
    app()
