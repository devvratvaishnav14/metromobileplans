"""Pricing tiers + current-offer handling.

A discounted price is only real for a customer who meets its conditions:
a $50 plan that needs Internet + AutoPay + a promo must NOT read as a universal
$50 plan.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from metromobile.pipeline import run_manual_import
from metromobile.pricing import price_view
from metromobile.providers.base import NormalizedPlan
from metromobile.serializers import build_plans_response
from metromobile.validation import validate_plan

NOW = dt.datetime(2026, 6, 1, 12, 0, tzinfo=dt.timezone.utc)
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CAPTURE = FIXTURES / "manual_example" / "capture.html"
BASE_MANIFEST = json.loads((FIXTURES / "manual_example" / "manifest.json").read_text())


def _plan(**kw) -> NormalizedPlan:
    base = dict(external_id="p", plan_name="P", price_period="monthly")
    base.update(kw)
    return NormalizedPlan(**base)


# --- tier resolution ------------------------------------------------
def test_unconditional_price_is_the_universal_price():
    pv = price_view(_plan(regular_price_cad=75, autopay_price_cad=65, bundle_price_cad=50), NOW)
    assert pv.universal_price_cad == 75
    assert pv.display_price_cad == 75
    assert pv.best_case_price_cad == 50
    assert pv.has_conditional_discounts is True
    labels = {t["label"] for t in pv.tiers}
    assert labels == {"regular", "with AutoPay", "with bundle"}


def test_only_conditional_prices_do_not_yield_a_universal_price():
    pv = price_view(
        _plan(bundle_price_cad=50, bundle_conditions="requires Bell Internet + AutoPay"), NOW
    )
    assert pv.universal_price_cad is None
    # never present the $50 conditional price as if universal
    assert pv.display_price_cad == 50
    assert "requires" in pv.price_note and "not recorded" in pv.price_note


def test_bundle_only_plan_is_not_rankable_until_the_base_price_is_added():
    r = validate_plan(
        _plan(bundle_price_cad=50, bundle_conditions="Bell Internet + AutoPay",
              data_full_speed_gb=60, data_unlimited=True, plan_type="postpaid",
              availability="online"),
        provider_known=True, source_url="https://x.test", now=NOW,
    )
    assert r.is_rankable is False
    assert any(i.field == "regular_price_cad" and "unconditional" in i.message for i in r.issues)

    r2 = validate_plan(
        _plan(regular_price_cad=75, bundle_price_cad=50, bundle_conditions="Bell Internet",
              data_full_speed_gb=60, data_unlimited=True, plan_type="postpaid",
              availability="online"),
        provider_known=True, source_url="https://x.test", now=NOW,
    )
    assert r2.is_rankable is True     # once the unconditional price is known


# --- current offer ------------------------------------------------
def test_active_universal_promo_lowers_the_effective_price():
    pv = price_view(
        _plan(regular_price_cad=55, promo_price_cad=40, promo_savings_cad=15,
              promo_ends_at=NOW + dt.timedelta(days=30)),
        NOW,
    )
    assert pv.is_current_offer and pv.offer_is_conditional is False
    assert pv.effective_price_cad == 40
    assert pv.savings_cad == 15


def test_conditional_promo_does_not_lower_the_default_users_price():
    pv = price_view(
        _plan(regular_price_cad=55, promo_price_cad=40,
              promo_stacks_conditions="also requires a Bell Internet bundle",
              promo_ends_at=NOW + dt.timedelta(days=30)),
        NOW,
    )
    assert pv.is_current_offer is True
    assert pv.offer_is_conditional is True
    assert pv.effective_price_cad == 55        # a default user still pays regular


def test_expired_promo_is_not_a_current_offer_and_price_reverts():
    pv = price_view(
        _plan(regular_price_cad=55, promo_price_cad=40, promo_ends_at=NOW - dt.timedelta(days=1)),
        NOW,
    )
    assert pv.offer_expired and not pv.is_current_offer and not pv.offer_active
    assert pv.effective_price_cad == 55
    assert "expired" in pv.offer_note


def test_promo_with_unknown_expiry_is_flagged_not_guessed():
    pv = price_view(_plan(regular_price_cad=55, promo_price_cad=45, promo_expiry_known=False), NOW)
    assert pv.offer_active is True
    assert "no end date" in pv.offer_note


# --- validation surfaces expiry problems -------------------------
def test_validation_warns_on_expired_promo():
    r = validate_plan(
        _plan(regular_price_cad=55, promo_price_cad=40, promo_ends_at=NOW - dt.timedelta(days=2),
              data_total_gb=10.0, plan_type="postpaid", availability="online"),
        provider_known=True, source_url="https://x.test", now=NOW,
    )
    assert any(i.field == "promo_ends_at" and "expired" in i.message for i in r.issues)


def test_validation_warns_when_expiry_unknown():
    r = validate_plan(
        _plan(regular_price_cad=55, promo_price_cad=40, promo_expiry_known=None,
              data_total_gb=10.0, plan_type="postpaid", availability="online"),
        provider_known=True, source_url="https://x.test", now=NOW,
    )
    assert any(i.field == "promo_expiry_known" for i in r.issues)


# --- end to end through the API --------------------------------
def test_expired_offer_not_counted_as_current_offer_in_api(session):
    now = dt.datetime.now(dt.timezone.utc)
    m = json.loads(json.dumps(BASE_MANIFEST))
    m["plans"] = [
        {**m["plans"][0], "external_id": "LIVE-OFFER", "plan_name": "Live Offer 30GB",
         "regular_price_cad": 55, "monthly_price_cad": 55,
         "promo_price_cad": 40, "promo_savings_cad": 15,
         "promo_ends_at": (now + dt.timedelta(days=20)).isoformat()},
        {**m["plans"][0], "external_id": "DEAD-OFFER", "plan_name": "Old Offer 30GB",
         "regular_price_cad": 60, "monthly_price_cad": 60,
         "promo_price_cad": 45,
         "promo_ends_at": (now - dt.timedelta(days=3)).isoformat()},
    ]
    run_manual_import(session, manifest=m, capture_path=CAPTURE, operator="t",
                      verified_at=now, source_mode="official_manual")

    by_id = {p.external_id: p for p in build_plans_response(session, "vancouver", now).plans}

    assert by_id["LIVE-OFFER"].is_current_offer is True
    assert by_id["LIVE-OFFER"].effective_price_cad == 40.0
    assert by_id["LIVE-OFFER"].offer_savings_cad == 15.0
    assert by_id["LIVE-OFFER"].universal_price_cad == 55.0

    assert by_id["DEAD-OFFER"].is_current_offer is False
    assert by_id["DEAD-OFFER"].offer_expired is True
    assert by_id["DEAD-OFFER"].effective_price_cad == 60.0
    assert any("expired" in i.message for i in by_id["DEAD-OFFER"].issues)


def test_promo_expiry_beats_a_still_fresh_capture(session):
    now = dt.datetime.now(dt.timezone.utc)
    m = json.loads(json.dumps(BASE_MANIFEST))
    m["plans"] = [{
        **m["plans"][0], "external_id": "PROMO-JUST-ENDED", "plan_name": "Promo 30GB",
        "regular_price_cad": 55, "monthly_price_cad": 55,
        "promo_price_cad": 40, "promo_expiry_known": True,
        "promo_ends_at": (now - dt.timedelta(hours=6)).isoformat(),
    }]
    run_manual_import(session, manifest=m, capture_path=CAPTURE, operator="t",
                      verified_at=now - dt.timedelta(days=2), source_mode="official_manual")

    p = {x.external_id: x for x in build_plans_response(session, "vancouver", now).plans}["PROMO-JUST-ENDED"]
    assert p.verification_status == "verified" and p.is_rankable is True
    assert p.is_current_offer is False and p.offer_expired is True
    assert p.effective_price_cad == 55.0


def test_bell_style_bundle_price_never_reads_as_universal(session):
    """The example principle: $50/mo only with Internet + AutoPay + promo must not
    rank as a universally available $50 plan."""
    now = dt.datetime.now(dt.timezone.utc)
    m = json.loads(json.dumps(BASE_MANIFEST))
    m["provider"]["slug"] = "bell"
    m["plans"] = [{
        "external_id": "bell-select-60", "plan_name": "Select - 60 GB", "plan_type": "postpaid",
        "price_period": "monthly", "availability": "online",
        "regular_price_cad": 75,
        "autopay_price_cad": 70, "autopay_conditions": "automatic payments",
        "bundle_price_cad": 50, "bundle_conditions": "requires Bell Internet + eligible streaming bundle",
        "promo_stacks_conditions": "price also includes a promotional credit",
        "data_full_speed_gb": 60, "data_unlimited": True, "throttle_speed": "512 Kbps",
        "canada_wide_calling": True, "unlimited_text": True,
    }]
    run_manual_import(session, manifest=m, capture_path=CAPTURE, operator="t",
                      verified_at=now, source_mode="official_manual")

    p = {x.external_id: x for x in build_plans_response(session, "vancouver", now).plans}["bell-select-60"]
    assert p.universal_price_cad == 75.0        # what a neutral ranking uses
    assert p.display_price_cad == 75.0          # not shown as $50
    assert p.best_case_price_cad == 50.0
    assert p.effective_price_cad == 75.0
    assert p.has_conditional_discounts is True
    assert any(t["label"] == "with bundle" and t["amount"] == 50 for t in p.price_tiers)
    assert p.is_rankable is True                # has an unconditional price
