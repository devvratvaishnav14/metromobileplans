from __future__ import annotations

import datetime as dt

from metromobile.models import Plan, RawDocument, RefreshRun
from metromobile.pipeline import run_manual_import, run_refresh
from metromobile.serializers import build_plans_response

from pathlib import Path
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

FIXTURE = FIXTURES / "chatr" / "plans_page.html"
EVIDENCE = FIXTURES / "manual_example" / "capture.html"

_BELL_MANIFEST = {
    "provider": {
        "slug": "bell", "display_name": "Bell", "network": "Bell", "plan_model": "postpaid",
    },
    "source": {"url": "https://www.bell.ca/Mobility/Bring-Your-Own-Phone", "kind": "capture"},
    "plans": [{
        "external_id": "bell-test-plan",
        "plan_name": "Test Plan",
        "regular_price_cad": 50,
        "price_period": "monthly",
        "plan_type": "postpaid",
        "data_total_gb": 20,
        "data_unlimited": False,
        "availability": "online",
    }],
}


def test_refresh_from_fixture_populates_store(session):
    outcome = run_refresh("chatr", session, fixture_path=FIXTURE)
    assert outcome.status == "success"
    assert outcome.records_seen == 7
    assert outcome.plans_upserted == 7
    assert outcome.plans_valid == 6  # the $100 400-min plan is held out
    assert outcome.plans_flagged == 1

    plans = session.query(Plan).all()
    assert len(plans) == 7
    assert {p.provider_slug for p in plans} == {"chatr"}
    # provenance is wired
    assert all(p.source_url == "https://www.chatrwireless.com/plans" for p in plans)
    assert all(p.raw_document_id for p in plans)
    assert session.query(RawDocument).count() == 1
    assert session.query(RefreshRun).one().status == "success"


def test_refresh_is_idempotent(session):
    run_refresh("chatr", session, fixture_path=FIXTURE)
    run_refresh("chatr", session, fixture_path=FIXTURE)
    assert session.query(Plan).count() == 7  # upsert, not duplicate


def test_public_mobile_is_reported_unavailable(session):
    outcome = run_refresh("public-mobile", session)
    assert outcome.status == "source_unavailable"
    assert "anti-bot" in (outcome.error_message or "")


def test_api_response_shape(session):
    run_refresh("chatr", session, fixture_path=FIXTURE)
    resp = build_plans_response(session, "burnaby", dt.datetime.now(dt.timezone.utc))

    assert resp.meta.municipality == "burnaby"
    assert resp.meta.municipality_affects_results is False
    assert resp.meta.provider_count == 1
    assert resp.meta.plan_count == 7
    assert resp.meta.rankable_count == 6
    assert resp.scores == []
    assert resp.profiles == []

    # sorted by price ascending, cheapest first
    prices = [p.monthly_price_cad or p.price_cad for p in resp.plans]
    assert prices == sorted(prices)

    cheapest = resp.plans[0]
    assert cheapest.provider_name == "Chatr Mobile"
    assert cheapest.source_url == "https://www.chatrwireless.com/plans"
    assert cheapest.freshness in {"fresh", "aging", "stale"}
    assert "verified" in cheapest.freshness_label.lower()


def test_meta_freshness_judges_each_plan_by_its_own_source_mode(session):
    """Regression test: meta.freshness must roll up the per-plan, source-mode-
    aware freshness values -- never re-judge the oldest timestamp against the
    official_automated default window (hours, not weeks). A manually verified
    plan that's comfortably within ITS OWN re-verify window must not drag the
    whole catalogue's aggregate down to "stale" just because it's older than an
    automated plan's few-hour freshness window."""
    now = dt.datetime.now(dt.timezone.utc)

    # official_automated: verified "just now" -> fresh under the automated window.
    run_refresh("chatr", session, fixture_path=FIXTURE)

    # official_manual: verified 5 days ago -> long past the automated window
    # (aging past 24h) but still "fresh" under the default manual window
    # (7-day fresh / 14-day reverify) -- exactly the mix production runs.
    run_manual_import(
        session, manifest=_BELL_MANIFEST, capture_path=EVIDENCE, operator="test",
        verified_at=now - dt.timedelta(days=5), source_mode="official_manual",
    )

    resp = build_plans_response(session, None, now)

    chatr_plan = next(p for p in resp.plans if p.provider_slug == "chatr")
    bell_plan = next(p for p in resp.plans if p.provider_slug == "bell")
    assert chatr_plan.freshness == "fresh"
    assert bell_plan.freshness == "fresh"  # would read "stale" if judged as automated

    # the aggregate must not regress to the old, automated-only default window
    assert resp.meta.freshness == "fresh"


def test_meta_freshness_still_reports_a_genuinely_stale_plan(session):
    """The fix must not overcorrect into always reporting "fresh": a plan that
    really is stale under its OWN source mode's window still drags the
    aggregate down."""
    now = dt.datetime.now(dt.timezone.utc)

    run_refresh("chatr", session, fixture_path=FIXTURE)  # fresh
    run_manual_import(
        session, manifest=_BELL_MANIFEST, capture_path=EVIDENCE, operator="test",
        verified_at=now - dt.timedelta(days=20),  # past the 14-day manual reverify window
        source_mode="official_manual",
    )

    resp = build_plans_response(session, None, now)

    bell_plan = next(p for p in resp.plans if p.provider_slug == "bell")
    assert bell_plan.freshness == "stale"
    assert resp.meta.freshness == "stale"
