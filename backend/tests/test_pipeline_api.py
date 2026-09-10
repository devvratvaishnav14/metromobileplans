from __future__ import annotations

import datetime as dt

from metromobile.models import Plan, RawDocument, RefreshRun
from metromobile.pipeline import run_refresh
from metromobile.serializers import build_plans_response

from pathlib import Path
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

FIXTURE = FIXTURES / "chatr" / "plans_page.html"


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
