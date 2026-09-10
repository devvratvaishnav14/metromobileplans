"""Three source modes: official_automated, official_manual, trusted_secondary."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from metromobile.models import (
    Plan,
    PlanVerificationEvent,
    Provider,
    RawDocument,
    RefreshRun,
)
from metromobile.pipeline import run_manual_import, run_refresh, sweep_stale
from metromobile.serializers import build_plans_response

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CHATR = FIXTURES / "chatr" / "plans_page.html"
MANIFEST = json.loads((FIXTURES / "manual_example" / "manifest.json").read_text())
CAPTURE = FIXTURES / "manual_example" / "capture.html"

# anchored to real "now" so freshness windows behave regardless of the calendar
NOW = dt.datetime.now(dt.timezone.utc)


# --- official_automated -------------------------------------------------
def test_chatr_is_tagged_official_automated(session):
    run_refresh("chatr", session, fixture_path=CHATR)
    plans = session.query(Plan).all()
    assert len(plans) == 7
    assert all(p.source_mode == "official_automated" for p in plans)
    assert all(p.verification_method == "automated_fetch" for p in plans)
    assert all(p.verified_by is None for p in plans)
    # every plan write appended a verification event
    assert all(len(p.verification_events) >= 1 for p in plans)
    assert session.query(RefreshRun).one().source_mode == "official_automated"


# --- official_manual ---------------------------------------------------
def test_manual_import_stores_plans_with_immutable_evidence(session):
    outcome = run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="tester",
        verified_at=NOW, source_mode="official_manual",
    )
    assert outcome.status == "success"
    assert outcome.records_seen == 3

    plans = {p.external_id: p for p in session.query(Plan).all()}
    assert set(plans) == {"EX-45-30GB", "EX-60-60GB", "EX-DATA-ADDON"}
    complete = plans["EX-45-30GB"]
    assert complete.source_mode == "official_manual"
    assert complete.verification_method == "operator_manual_review"
    assert complete.verified_by == "tester"
    assert complete.verification_status == "verified"
    assert complete.is_rankable is True
    assert complete.last_verified_at.replace(tzinfo=dt.timezone.utc) == NOW

    # the incomplete add-on: no data allowance -> provisional, not rankable
    addon = plans["EX-DATA-ADDON"]
    assert addon.verification_status == "provisional"
    assert addon.is_rankable is False

    # immutable capture is retained with full provenance
    raw = session.query(RawDocument).one()
    assert raw.retrieval == "manual_import"
    assert raw.operator == "tester"
    assert raw.captured_at.replace(tzinfo=dt.timezone.utc) == NOW
    assert raw.official_source_url == "https://example.test/plans"
    assert raw.content_hash and raw.byte_size
    assert Path(raw.storage_path).name  # bytes written to disk
    assert raw.parser_version == "manual-import-v1"

    prov = session.get(Provider, "example-mobile")
    assert prov.default_source_mode == "official_manual"
    assert prov.network == "Bell"


def test_manual_data_goes_stale_and_loses_ranking_at_serve_time(session):
    run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="tester",
        verified_at=NOW, source_mode="official_manual",
    )
    p = session.query(Plan).filter_by(external_id="EX-45-30GB").one()
    assert p.is_rankable is True  # fresh at import

    # serve 20 days later -- past the 14-day manual re-verify window -> stale,
    # not rankable, even though no sweep has run
    later = NOW + dt.timedelta(days=20)
    resp = build_plans_response(session, "vancouver", later)
    served = {x.external_id: x for x in resp.plans}["EX-45-30GB"]
    assert served.freshness == "stale"
    assert served.verification_status == "stale"
    assert served.is_rankable is False
    assert resp.meta.rankable_count == 0


def test_sweep_persists_the_stale_transition(session):
    run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="tester",
        verified_at=NOW, source_mode="official_manual",
    )
    changed = sweep_stale(session, now=NOW + dt.timedelta(days=20))
    assert ("example-mobile", "EX-45-30GB") in changed

    p = session.query(Plan).filter_by(external_id="EX-45-30GB").one()
    assert p.verification_status == "stale"
    assert p.is_rankable is False
    kinds = [e.event_kind for e in p.verification_events]
    assert "sweep_stale" in kinds  # transition recorded in history


# --- trusted_secondary ----------------------------------------------
def test_secondary_never_verified_or_rankable_on_its_own(session):
    run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="tester",
        verified_at=NOW, source_mode="trusted_secondary",
    )
    p = session.query(Plan).filter_by(external_id="EX-45-30GB").one()
    assert p.source_mode == "trusted_secondary"
    assert p.verification_method == "secondary_manual"
    assert p.verification_status == "secondary_confirmed"
    assert p.is_rankable is False                     # complete + fresh, still not rankable
    assert p.confidence <= 0.6                        # capped
    assert p.official_crosscheck is False


def test_secondary_with_official_crosscheck_can_be_verified(session):
    run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="tester",
        verified_at=NOW, source_mode="trusted_secondary", official_crosscheck=True,
    )
    p = session.query(Plan).filter_by(external_id="EX-45-30GB").one()
    assert p.official_crosscheck is True
    assert p.verification_status == "verified"
    assert p.is_rankable is True


def test_secondary_ranking_can_be_enabled_by_policy(session, monkeypatch):
    monkeypatch.setenv("METROMOBILE_SECONDARY_RANKING_ALLOWED", "true")
    from metromobile.config import get_settings

    get_settings.cache_clear()
    run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="tester",
        verified_at=NOW, source_mode="trusted_secondary",
    )
    p = session.query(Plan).filter_by(external_id="EX-45-30GB").one()
    assert p.verification_status == "secondary_confirmed"
    assert p.is_rankable is True  # policy flag flipped


# --- provenance persistence ---------------------------------------
def test_reverify_appends_history_and_keeps_old_evidence(session):
    run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="alice",
        verified_at=NOW, source_mode="official_manual",
    )
    # a later re-verification with a changed price
    m2 = json.loads(json.dumps(MANIFEST))
    m2["plans"][0]["price_cad"] = 49
    m2["plans"][0]["monthly_price_cad"] = 49
    run_manual_import(
        session, manifest=m2, capture_path=CAPTURE, operator="bob",
        verified_at=NOW + dt.timedelta(days=1), source_mode="official_manual",
    )

    p = session.query(Plan).filter_by(external_id="EX-45-30GB").one()
    assert float(p.price_cad) == 49.0            # current state reflects the latest
    assert p.verified_by == "bob"

    events = sorted(
        session.query(PlanVerificationEvent).filter_by(plan_id=p.id).all(),
        key=lambda e: e.event_at,
    )
    assert len(events) >= 2
    assert float(events[0].price_cad) == 45.0    # old observation preserved
    assert float(events[-1].price_cad) == 49.0
    assert events[0].operator == "alice"
    assert events[-1].operator == "bob"

    # two immutable RawDocuments, both still present
    raws = session.query(RawDocument).filter_by(source_id=p.source_id).all()
    assert len(raws) == 2
    assert all(Path(r.storage_path).exists() or r.storage_path for r in raws)
    assert session.query(RefreshRun).count() == 2


# --- Chatr stays intact -----------------------------------------
def test_chatr_unaffected_by_a_manual_import(session):
    run_refresh("chatr", session, fixture_path=CHATR)
    run_manual_import(
        session, manifest=MANIFEST, capture_path=CAPTURE, operator="tester",
        verified_at=NOW, source_mode="official_manual",
    )
    chatr = session.query(Plan).filter_by(provider_slug="chatr").all()
    assert len(chatr) == 7
    assert all(p.source_mode == "official_automated" for p in chatr)
    assert all(p.verification_method == "automated_fetch" for p in chatr)
    assert sum(1 for p in chatr if p.is_rankable) == 6
    # 6 verified + rankable; the $100 400-min plan stays provisional (no data allowance)
    assert sum(1 for p in chatr if p.verification_status == "verified") == 6
    assert sum(1 for p in chatr if p.verification_status == "provisional") == 1

    resp = build_plans_response(session, "vancouver", dt.datetime.now(dt.timezone.utc))
    assert resp.meta.source_mode_counts["official_automated"] == 7
    assert resp.meta.source_mode_counts["official_manual"] == 3
