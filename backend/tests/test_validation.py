from __future__ import annotations

import datetime as dt

from metromobile.providers.base import NormalizedPlan
from metromobile.validation import (
    INVALID,
    PROVISIONAL,
    SECONDARY_CONFIRMED,
    STALE_STATUS,
    VERIFIED,
    validate_plan,
)

SRC = "https://example.test/plans"
NOW = dt.datetime(2026, 9, 3, 12, 0, tzinfo=dt.timezone.utc)


def _plan(**kw) -> NormalizedPlan:
    base = dict(
        external_id="x1",
        plan_name="Test 10GB",
        regular_price_cad=30.0,
        monthly_price_cad=30.0,
        price_cad=30.0,
        price_period="monthly",
        data_total_gb=10.0,
        data_unlimited=False,
        plan_type="prepaid",
        availability="online",
    )
    base.update(kw)
    return NormalizedPlan(**base)


def test_complete_plan_is_verified_and_rankable():
    r = validate_plan(_plan(), provider_known=True, source_url=SRC)
    assert r.verification_status == VERIFIED
    assert r.is_rankable is True
    assert not r.errors


def test_negative_price_is_a_hard_error():
    r = validate_plan(
        _plan(regular_price_cad=-1.0, monthly_price_cad=-1.0, price_cad=-1.0),
        provider_known=True, source_url=SRC,
    )
    assert r.verification_status == INVALID
    assert r.is_rankable is False
    assert any("negative" in i.message for i in r.errors)


def test_missing_price_is_invalid():
    r = validate_plan(
        _plan(regular_price_cad=None, monthly_price_cad=None, price_cad=None, price_period=None),
        provider_known=True,
        source_url=SRC,
    )
    assert r.verification_status == INVALID
    assert r.is_rankable is False


def test_missing_data_allowance_is_provisional_not_rankable():
    r = validate_plan(
        _plan(data_total_gb=None, data_unlimited=None),
        provider_known=True,
        source_url=SRC,
    )
    assert r.verification_status == PROVISIONAL
    assert r.is_rankable is False
    assert r.confidence < 1.0


def test_no_source_url_is_error():
    r = validate_plan(_plan(), provider_known=True, source_url=None)
    assert any(i.field == "source_url" for i in r.errors)


def test_name_claims_gb_but_no_data_parsed_warns():
    r = validate_plan(
        _plan(plan_name="Big 50GB Plan", data_total_gb=None, data_unlimited=None),
        provider_known=True,
        source_url=SRC,
    )
    assert any(i.severity == "warning" and i.field == "data_total_gb" for i in r.issues)


# --- per-mode rules -------------------------------------------------
def test_official_manual_fresh_is_verified_and_rankable():
    r = validate_plan(
        _plan(), provider_known=True, source_url=SRC, source_mode="official_manual",
        last_verified_at=NOW - dt.timedelta(hours=1), now=NOW,
    )
    assert r.verification_status == VERIFIED
    assert r.is_rankable is True


def test_official_manual_past_reverify_window_is_stale_and_unrankable():
    r = validate_plan(
        _plan(), provider_known=True, source_url=SRC, source_mode="official_manual",
        last_verified_at=NOW - dt.timedelta(days=20), now=NOW,  # > 14-day window
    )
    assert r.verification_status == STALE_STATUS
    assert r.is_rankable is False


def test_official_manual_capture_one_week_old_is_still_fresh():
    r = validate_plan(
        _plan(), provider_known=True, source_url=SRC, source_mode="official_manual",
        last_verified_at=NOW - dt.timedelta(days=6), now=NOW,
    )
    assert r.verification_status == VERIFIED
    assert r.is_rankable is True


def test_trusted_secondary_alone_is_never_verified_or_rankable():
    r = validate_plan(
        _plan(), provider_known=True, source_url=SRC, source_mode="trusted_secondary",
        last_verified_at=NOW, now=NOW,
    )
    assert r.verification_status == SECONDARY_CONFIRMED
    assert r.is_rankable is False
    assert r.confidence <= 0.6


def test_eligibility_restricted_plan_is_verified_but_not_default_rankable():
    r = validate_plan(
        _plan(eligibility_restricted=True,
              eligibility_conditions="Bell employees only"),
        provider_known=True, source_url=SRC,
    )
    assert r.verification_status == VERIFIED   # it is a real, verified plan
    assert r.is_rankable is False              # ... just not for an ordinary user
    assert any(i.field == "eligibility_restricted" for i in r.issues)


def test_trusted_secondary_with_crosscheck_may_be_verified():
    r = validate_plan(
        _plan(), provider_known=True, source_url=SRC, source_mode="trusted_secondary",
        last_verified_at=NOW, now=NOW, official_crosscheck=True,
    )
    assert r.verification_status == VERIFIED
    assert r.is_rankable is True
