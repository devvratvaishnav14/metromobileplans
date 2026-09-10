"""Re-verification: a newer capture updates the plan but never loses history."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from metromobile.cli import _strip_jsonc
from metromobile.models import Plan, PlanVerificationEvent, RawDocument, RefreshRun
from metromobile.pipeline import run_manual_import

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CAPTURE = FIXTURES / "manual_example" / "capture.html"

MANIFEST_V1 = {
    "provider": {"slug": "bell", "display_name": "Bell", "network": "Bell", "plan_model": "postpaid"},
    "source": {"url": "https://www.bell.ca/Mobility/Cell_phone_plans", "kind": "capture"},
    "plans": [
        {
            "external_id": "bell-unlimited-100gb",
            "plan_name": "Unlimited 100GB",
            "plan_type": "postpaid",
            "price_period": "monthly",
            "monthly_price_cad": 85,
            "regular_price_cad": 95,
            "data_total_gb": 100,
            "data_full_speed_gb": 100,
            "data_unlimited": True,
            "data_unlimited_is_full_speed": False,
            "network_technology": "5G",
            "has_5g": True,
            "canada_wide_calling": True,
            "unlimited_text": True,
            "autopay_required": True,
            "contract_required": False,
            "byod": True,
            "availability": "online",
        },
        {
            "external_id": "bell-unlimited-75gb",
            "plan_name": "Unlimited 75GB",
            "plan_type": "postpaid",
            "price_period": "monthly",
            "monthly_price_cad": 75,
            "data_total_gb": 75,
            "data_unlimited": True,
            "plan_type_ok": True,
            "canada_wide_calling": True,
            "unlimited_text": True,
            "availability": "online",
        },
    ],
}


def test_reverify_updates_plan_and_appends_history(session):
    t1 = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
    run_manual_import(
        session, manifest=MANIFEST_V1, capture_path=CAPTURE, operator="alice",
        verified_at=t1, source_mode="official_manual",
    )

    # a newer capture: 100GB plan price rose, 75GB plan discontinued, a new plan added
    v2 = json.loads(json.dumps(MANIFEST_V1))
    v2["plans"][0]["monthly_price_cad"] = 90
    v2["plans"][0]["data_total_gb"] = 120
    v2["plans"].pop(1)  # 75GB gone
    v2["plans"].append({
        "external_id": "bell-40gb",
        "plan_name": "40GB",
        "plan_type": "postpaid",
        "price_period": "monthly",
        "monthly_price_cad": 55,
        "data_total_gb": 40,
        "data_unlimited": False,
        "data_hard_cap": True,
        "canada_wide_calling": True,
        "unlimited_text": True,
        "availability": "online",
    })
    t2 = dt.datetime.now(dt.timezone.utc)
    run_manual_import(
        session, manifest=v2, capture_path=CAPTURE, operator="bob",
        verified_at=t2, source_mode="official_manual",
        note="quarterly re-check", event_kind="reverify",
    )

    plans = {p.external_id: p for p in session.query(Plan).filter_by(provider_slug="bell")}

    # 100GB plan reflects the LATEST values
    p100 = plans["bell-unlimited-100gb"]
    assert float(p100.monthly_price_cad) == 90.0
    assert p100.data_total_gb == 120.0
    assert p100.verified_by == "bob"

    # ...but its history keeps the FIRST observation intact
    evts = sorted(
        session.query(PlanVerificationEvent).filter_by(plan_id=p100.id).all(),
        key=lambda e: e.event_at,
    )
    assert len(evts) == 2
    assert float(evts[0].price_cad) == 85.0 and evts[0].operator == "alice"
    assert float(evts[1].price_cad) == 90.0 and evts[1].operator == "bob"
    assert evts[1].event_kind == "reverify"
    assert evts[1].note == "quarterly re-check"

    # discontinued plan: flagged invalid, NOT deleted, with a vanished event
    p75 = plans["bell-unlimited-75gb"]
    assert p75.verification_status == "invalid"
    assert p75.is_rankable is False
    assert any(e.event_kind == "vanished" for e in p75.verification_events)

    # new plan present
    assert "bell-40gb" in plans

    # both immutable captures retained
    assert session.query(RawDocument).filter(RawDocument.retrieval == "manual_import").count() == 2
    assert session.query(RefreshRun).count() == 2


def test_jsonc_stripper_keeps_urls_drops_comments():
    src = """
    // a header comment
    {
      "source": { "url": "https://www.bell.ca/Mobility/Cell_phone_plans" }, // trailing note
      /* block
         comment */
      "plans": [
        { "external_id": "x", "note": "a // b inside a string stays" },
      ]
    }
    """
    d = json.loads(_strip_jsonc(src))
    assert d["source"]["url"] == "https://www.bell.ca/Mobility/Cell_phone_plans"
    assert d["plans"][0]["note"] == "a // b inside a string stays"


def test_all_shipped_templates_parse():
    templates = sorted((FIXTURES.parent / "imports").glob("*/manifest.template.jsonc"))
    assert len(templates) == 4
    for t in templates:
        d = json.loads(_strip_jsonc(t.read_text()))
        assert d["provider"]["slug"] in {"bell", "koodo", "freedom-mobile", "rogers"}
        assert d["source"]["url"].startswith("https://")
        assert isinstance(d["plans"], list) and d["plans"]
