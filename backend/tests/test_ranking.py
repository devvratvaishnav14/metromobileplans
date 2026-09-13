"""Tests for the V1 ranking engine (metromobile.ranking).

Two kinds of coverage:
* Unit tests against the pure scoring functions -- fast, isolate one formula
  at a time, no DB.
* Regression tests against the real, approved V1 four-provider dataset
  (fixtures/ranking/v1_dataset.json, a snapshot of the frozen dataset) --
  assert the exact Top-5 ordering for all five presets matches the simulation
  that was reviewed and approved before this code was written. If one of
  these breaks, the ranking output changed -- that's the whole point.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from metromobile.models import Plan
from metromobile.pipeline import run_manual_import
from metromobile.pricing import price_view
from metromobile.providers.base import NormalizedPlan
from metromobile.ranking import (
    CHEAPEST,
    MOST_DATA,
    OFFERS,
    OVERALL,
    STUDENTS,
    CustomFilters,
    RankingContext,
    _is_student_unlocked,
    data_gb,
    data_score,
    features_score,
    passes_filters,
    price_score,
    rank_plans,
    roaming_score,
    technology_score,
    weighted_total,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CAPTURE = FIXTURES / "manual_example" / "capture.html"
DATASET = json.loads((FIXTURES / "ranking" / "v1_dataset.json").read_text())
NOW = dt.datetime(2026, 9, 10, 12, 0, tzinfo=dt.timezone.utc)


def _plan(**kw) -> NormalizedPlan:
    base = dict(external_id="p", plan_name="P", price_period="monthly")
    base.update(kw)
    return NormalizedPlan(**base)


def _import_v1_dataset(session, now: dt.datetime = NOW) -> None:
    for block in DATASET.values():
        manifest = {"provider": block["provider"], "source": block["source"], "plans": block["plans"]}
        run_manual_import(
            session, manifest=manifest, capture_path=CAPTURE, operator="test",
            verified_at=now, source_mode="official_manual",
        )


def _by_id(ranking_result):
    return {r.plan.external_id: r for r in ranking_result.results}


@pytest.fixture
def api():
    """A FastAPI TestClient + the Session it serves from, sharing one in-memory
    SQLite DB across the TestClient's worker thread (StaticPool)."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from metromobile.api import app
    from metromobile.db import Base, get_session

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
    app.dependency_overrides[get_session] = lambda: session
    try:
        yield SimpleNamespace(client=TestClient(app), session=session)
    finally:
        app.dependency_overrides.clear()
        session.close()


# =====================================================================
# Unit tests -- component formulas
# =====================================================================

class TestMonthlyEquivalentPrice:
    def test_annual_plan_normalizes_to_monthly_equivalent(self):
        pv = price_view(_plan(regular_price_cad=159, price_period="annual", term_months=12), NOW)
        assert pv.monthly_equivalent_price_cad == 13.25
        # the original amount + period must be preserved, not overwritten
        assert pv.universal_price_cad == 159
        assert pv.upfront_price_cad == 159
        assert pv.term_months == 12
        assert pv.billing_period == "annual"

    def test_monthly_plan_is_unchanged(self):
        pv = price_view(_plan(regular_price_cad=55, price_period="monthly"), NOW)
        assert pv.monthly_equivalent_price_cad == 55
        assert pv.upfront_price_cad is None


class TestPriceScore:
    def test_bounds(self):
        assert price_score(10) == 100.0
        assert price_score(120) == 0.0
        assert price_score(5) == 100.0   # clamped
        assert price_score(200) == 0.0   # clamped
        assert price_score(None) is None

    def test_chatr_annual_scores_as_cheapest_not_most_expensive(self):
        # $159/12mo must score like $13.25/mo, not like a $159/mo plan
        assert price_score(13.25) > price_score(55)


class TestDataScore:
    @pytest.mark.parametrize("gb,expected", [
        (0.25, 3.8), (3, 23.8), (20, 52.3), (100, 79.3), (125, 83.2), (175, 88.9), (250, 95.0),
    ])
    def test_finite_targets(self, gb, expected):
        assert data_score(gb) == pytest.approx(expected, abs=0.1)

    def test_unlimited_is_max_and_beats_every_finite_value(self):
        assert data_score("UNLIMITED") == 100.0
        assert data_score("UNLIMITED") > data_score(250)

    def test_finite_data_is_capped_at_95(self):
        assert data_score(250) == pytest.approx(95.0, abs=0.05)
        assert data_score(10_000) == 95.0  # never reaches/exceeds the unlimited score

    def test_known_zero_allowance(self):
        assert data_score(0.0) == 0.0

    def test_missing_is_none(self):
        assert data_score(None) is None

    def test_more_finite_gb_always_scores_higher(self):
        assert data_score(250) > data_score(175) > data_score(100) > data_score(20)


class TestDataGbFallbackChain:
    def test_full_speed_field_used_first(self):
        assert data_gb(_plan(data_full_speed_gb=70, data_total_gb=999)) == 70

    def test_falls_back_to_total_gb(self):
        assert data_gb(_plan(data_total_gb=20)) == 20

    def test_unlimited_full_speed_sentinel(self):
        assert data_gb(_plan(data_unlimited_is_full_speed=True, data_full_speed_gb=None)) == "UNLIMITED"

    def test_known_no_data_allowance(self):
        assert data_gb(_plan(data_unlimited=False)) == 0.0

    def test_genuinely_unresolvable_is_none(self):
        assert data_gb(_plan()) is None


class TestTechnologyScore:
    @pytest.mark.parametrize("tech,score", [
        ("5G+", 100.0), ("5G", 85.0), ("4G LTE", 60.0), ("4G", 60.0), ("3G", 30.0),
    ])
    def test_tiers(self, tech, score):
        assert technology_score(_plan(network_technology=tech)) == score

    def test_unknown_is_none_not_zero(self):
        assert technology_score(_plan(network_technology=None)) is None


class TestFeaturesScore:
    def test_all_known_true(self):
        f = features_score(_plan(canada_wide_calling=True, unlimited_text=True, hotspot=True))
        assert f == 100.0

    def test_talk_false_penalizes_but_does_not_zero(self):
        f = features_score(_plan(canada_wide_calling=False, unlimited_text=True, hotspot=False))
        # 0.55*40 + 0.30*100 + 0.15*50 = 59.5
        assert f == pytest.approx(59.5)

    def test_hotspot_unknown_is_neutral_not_penalized(self):
        f_unknown = features_score(_plan(canada_wide_calling=True, unlimited_text=True, hotspot=None))
        f_false = features_score(_plan(canada_wide_calling=True, unlimited_text=True, hotspot=False))
        assert f_unknown == f_false  # both read as the neutral 50 -- hotspot has no True/False distinction stored

    def test_annual_billing_does_not_affect_features_score(self):
        # payment flexibility was removed as a scored term -- annual vs monthly
        # billing must not move this score at all.
        monthly = features_score(_plan(canada_wide_calling=True, unlimited_text=True, hotspot=False,
                                        price_period="monthly"))
        annual = features_score(_plan(canada_wide_calling=True, unlimited_text=True, hotspot=False,
                                       price_period="annual", term_months=12))
        assert monthly == annual


class TestRoamingScore:
    def test_canada_us_mexico(self):
        assert roaming_score(_plan(includes_us=True, includes_mexico=True)) == 100.0

    def test_us_only(self):
        assert roaming_score(_plan(includes_us=True, includes_mexico=False)) == 75.0

    def test_international_without_us_or_mexico(self):
        assert roaming_score(_plan(international_roaming=True)) == 80.0

    def test_none_advertised_scores_zero_not_missing(self):
        assert roaming_score(_plan()) == 0.0

    def test_freedom_style_capped_at_100_not_stacked(self):
        # includes_us + includes_mexico + a SEPARATE Roam Beyond allowance
        # (international_roaming=True) must still cap at 100, never exceed it.
        assert roaming_score(_plan(includes_us=True, includes_mexico=True, international_roaming=True)) == 100.0


class TestWeightedTotalRedistribution:
    def test_missing_component_is_excluded_and_weight_redistributed(self):
        weights = {"price": 30, "data": 30, "technology": 10, "features": 15, "roaming": 5, "offer": 10}
        components = {"price": 80.0, "data": 80.0, "technology": None, "features": 80.0, "roaming": 80.0, "offer": 80.0}
        # every present component is 80 -> regardless of redistribution, total must stay 80
        assert weighted_total(components, weights) == 80.0

    def test_all_missing_is_none(self):
        weights = {"price": 30, "data": 30, "technology": 10, "features": 15, "roaming": 5, "offer": 10}
        components = {k: None for k in weights}
        assert weighted_total(components, weights) is None


# =====================================================================
# Candidate pool / eligibility
# =====================================================================

class TestEligibilityGating:
    def test_restricted_student_plan_excluded_by_default(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, OVERALL, RankingContext(), NOW, limit=50)
        ids = {r.plan.external_id for r in res.results}
        assert "total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer" not in ids
        assert "koodo-10gb-5g-student-deal" not in ids

    def test_student_eligible_true_unlocks_freedom_student_variant(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, STUDENTS, RankingContext(student_eligible=True), NOW, limit=50)
        ids = {r.plan.external_id for r in res.results}
        assert "total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer" in ids

    def test_koodo_student_deal_excluded_by_default_unlocked_when_eligible(self, session):
        """koodo-10gb-5g-student-deal: excluded from every default (non-student)
        ranking, and appears once the user confirms student eligibility -- same
        contract as the Freedom student variant above."""
        _import_v1_dataset(session)

        default = rank_plans(session, OVERALL, RankingContext(), NOW, limit=50)
        assert "koodo-10gb-5g-student-deal" not in {r.plan.external_id for r in default.results}

        unlocked = rank_plans(session, STUDENTS, RankingContext(student_eligible=True), NOW, limit=50)
        assert "koodo-10gb-5g-student-deal" in {r.plan.external_id for r in unlocked.results}

    def test_student_unlock_comes_from_the_student_offer_flag_not_a_text_search(self):
        """_is_student_unlocked must key off the explicit student_offer flag --
        not incidentally off the word "student" appearing somewhere in
        eligibility_conditions. Proven with a plan whose conditions text
        contains no such word at all: it must still unlock on the flag alone."""
        plan = Plan(
            eligibility_restricted=True,
            student_offer=True,
            eligibility_conditions="auto-pay by bank account discount; no matching keyword present here",
        )
        assert "student" not in (plan.eligibility_conditions or "").lower()
        assert _is_student_unlocked(plan) is True

        # a plan that isn't restricted at all never unlocks, flag or no flag
        not_restricted = Plan(eligibility_restricted=False, student_offer=True)
        assert _is_student_unlocked(not_restricted) is False

    def test_student_ineligible_never_uses_the_discounted_price(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, OVERALL, RankingContext(student_eligible=False), NOW, limit=50)
        ids = {r.plan.external_id for r in res.results}
        assert "total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer" not in ids

    def test_freedom_student_price_used_is_discounted_but_offer_reference_stays_regular(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, STUDENTS, RankingContext(student_eligible=True), NOW, limit=50)
        r = _by_id(res)["total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer"]
        assert r.price_used_cad == 45.0                    # Price component: discounted
        assert r.regular_reference_price_cad == 55.0        # Offer component: always the regular price
        assert r.offer_detail is not None
        assert r.offer_detail.dollar_savings_cad == 10.0
        assert r.offer_detail.offer_score == pytest.approx(48.28, abs=0.01)
        assert r.offer_score > 0                             # never zeroed out by qualifying


class TestBestCurrentOffersCandidatePool:
    def test_excludes_zero_offer_plans(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, OFFERS, RankingContext(), NOW, limit=50)
        assert all((r.offer_score or 0) > 0 for r in res.results)
        # Chatr has no conditional tiers at all -> O=0 -> must never appear here
        chatr_ids = {r.plan.external_id for r in res.results if r.plan.provider_slug == "chatr"}
        assert chatr_ids == set()


class TestAutopayContext:
    def test_autopay_willing_swaps_price_for_autopay_only_plans(self, session):
        _import_v1_dataset(session)
        default = _by_id(rank_plans(session, OVERALL, RankingContext(), NOW, limit=50))
        willing = _by_id(rank_plans(session, OVERALL, RankingContext(autopay_willing=True), NOW, limit=50))
        plan_id = "total-freedom-175gb-roam-beyond-10gb"
        assert default[plan_id].price_used_cad == 55.0
        assert willing[plan_id].price_used_cad == 50.0
        # confirming autopay willingness must not change the fixed Offer reference
        assert willing[plan_id].regular_reference_price_cad == 55.0


# =====================================================================
# Ordering / tie-breaking
# =====================================================================

class TestMostDataOrdering:
    def test_finite_data_ordering(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, MOST_DATA, RankingContext(), NOW, limit=50)
        by_id = _by_id(res)
        assert by_id["total-freedom-250gb-roam-beyond-10gb"].data_score > \
               by_id["total-freedom-175gb-roam-beyond-10gb"].data_score

    def test_unlimited_beats_every_finite_plan(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, MOST_DATA, RankingContext(), NOW, limit=1)
        assert res.results[0].plan.provider_slug == "bell"
        assert res.results[0].data_score == 100.0

    def test_throttled_continuation_beats_hard_stop_on_equal_allowance(self, session):
        now = NOW
        manifest = {
            "provider": {"slug": "tie-test", "display_name": "Tie Test", "network": None,
                         "plan_model": "postpaid", "homepage_url": "https://x.test"},
            "source": {"url": "https://x.test/plans", "kind": "capture"},
            "plans": [
                {"external_id": "continues", "plan_name": "Continues 50GB", "price_period": "monthly",
                 "regular_price_cad": 50, "data_full_speed_gb": 50, "data_unlimited": True,
                 "data_hard_cap": False, "plan_type": "postpaid", "availability": "online"},
                {"external_id": "stops", "plan_name": "Stops 50GB", "price_period": "monthly",
                 "regular_price_cad": 50, "data_full_speed_gb": 50, "data_unlimited": False,
                 "data_hard_cap": True, "plan_type": "postpaid", "availability": "online"},
            ],
        }
        run_manual_import(session, manifest=manifest, capture_path=CAPTURE, operator="test",
                           verified_at=now, source_mode="official_manual")
        res = rank_plans(session, MOST_DATA, RankingContext(), now, limit=2)
        assert [r.plan.external_id for r in res.results] == ["continues", "stops"]


class TestDeterministicTieBreaking:
    def test_identical_plans_break_ties_by_external_id(self, session):
        now = NOW
        base = dict(price_period="monthly", regular_price_cad=50, data_full_speed_gb=50,
                    data_unlimited=True, data_hard_cap=False, plan_type="postpaid",
                    availability="online", network_technology="5G")
        manifest = {
            "provider": {"slug": "tie-test-2", "display_name": "Tie Test 2", "network": None,
                         "plan_model": "postpaid", "homepage_url": "https://x.test"},
            "source": {"url": "https://x.test/plans2", "kind": "capture"},
            "plans": [
                {**base, "external_id": "zzz-last", "plan_name": "Z"},
                {**base, "external_id": "aaa-first", "plan_name": "A"},
            ],
        }
        run_manual_import(session, manifest=manifest, capture_path=CAPTURE, operator="test",
                           verified_at=now, source_mode="official_manual")
        res = rank_plans(session, OVERALL, RankingContext(), now, limit=2)
        assert [r.plan.external_id for r in res.results] == ["aaa-first", "zzz-last"]


class TestMunicipalityHasNoEffect:
    @pytest.mark.parametrize("preset", [OVERALL, STUDENTS, CHEAPEST, MOST_DATA, OFFERS])
    def test_same_scores_regardless_of_municipality(self, session, preset):
        _import_v1_dataset(session)
        muni_results = {}
        for muni in (None, "vancouver", "burnaby", "surrey"):
            res = rank_plans(session, preset, RankingContext(municipality=muni), NOW, limit=10)
            muni_results[muni] = [(r.plan.external_id, r.final_score) for r in res.results]
        values = list(muni_results.values())
        assert all(v == values[0] for v in values)


# =====================================================================
# Regression: exact Top-5 from the approved simulation
# =====================================================================

class TestApprovedSimulationRegression:
    def test_best_overall_top5_is_all_freedom(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, OVERALL, RankingContext(), NOW, limit=5)
        ids = [r.plan.external_id for r in res.results]
        assert ids == [
            "total-freedom-175gb-roam-beyond-10gb",
            "total-freedom-125gb-roam-beyond-5gb",
            "total-freedom-250gb-roam-beyond-10gb",
            "total-freedom-70gb-roam-beyond-1gb",
            "total-freedom-250gb-roam-beyond-20gb",
        ]
        assert all(r.plan.provider_slug == "freedom-mobile" for r in res.results)
        scores = [r.final_score for r in res.results]
        assert scores == pytest.approx([75.63, 75.43, 74.48, 74.04, 71.57], abs=0.01)

    def test_cheapest_top5(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, CHEAPEST, RankingContext(), NOW, limit=5)
        ids = [r.plan.external_id for r in res.results]
        assert ids == ["4014", "koodo-250mb-3g", "5156", "5157", "5159"]
        # the annual Chatr plan must rank on its $13.25/mo equivalent, not $159
        assert res.results[0].price_used_cad == 13.25
        assert res.results[0].commitment == {"upfront_cad": 159.0, "term_months": 12}

    def test_most_data_top5(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, MOST_DATA, RankingContext(), NOW, limit=5)
        ids = [r.plan.external_id for r in res.results]
        # 5th slot updated 2026-09-13: the 3 new 250GB Freedom tiers (30/40/50GB
        # Roam Beyond) tie every existing 250GB Freedom plan on data_score (data
        # is capped by the log scale at 250GB); among that 5-way tie the 3
        # cheapest win the remaining Top-5 slots after the two Bell Unlimited
        # plans -- 10GB, 20GB, then the new 30GB Roam Beyond, which displaces the
        # previously-5th total-freedom-175gb-roam-beyond-10gb (lower raw GB, so a
        # lower data_score than any 250GB-tier plan).
        assert ids == [
            "bell-ultra-unlimited-with-u-s-mexico-roaming",
            "bell-ultra-unlimited-with-international-roaming",
            "total-freedom-250gb-roam-beyond-10gb",
            "total-freedom-250gb-roam-beyond-20gb",
            "total-freedom-250gb-roam-beyond-30gb",
        ]

    def test_best_current_offers_top5_is_mixed_bell_and_freedom(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, OFFERS, RankingContext(), NOW, limit=5)
        ids = [r.plan.external_id for r in res.results]
        assert ids == [
            "bell-ultra-unlimited-with-u-s-mexico-roaming",
            "bell-select-100-gb-with-u-s-roaming",
            "total-freedom-70gb-roam-beyond-1gb",
            "total-freedom-125gb-roam-beyond-5gb",
            "total-freedom-175gb-roam-beyond-10gb",
        ]
        providers = {r.plan.provider_slug for r in res.results}
        assert providers == {"bell", "freedom-mobile"}   # no provider-diversity manipulation needed

    def test_freedom_gains_three_new_250gb_roam_beyond_tiers(self, session):
        """Added 2026-09-13 from a fresh Freedom BC capture: three additional
        standalone 250GB plans (30/40/50GB Roam Beyond), each a flat $5/mo
        Digital Discount off its regular price -- same mechanism as every other
        Freedom plan."""
        _import_v1_dataset(session)
        by_id = {
            p.external_id: p
            for p in session.scalars(select(Plan)).all()
            if p.provider_slug == "freedom-mobile"
        }
        assert len(by_id) == 10

        expected = {
            "total-freedom-250gb-roam-beyond-30gb": (85.0, 80.0),
            "total-freedom-250gb-roam-beyond-40gb": (95.0, 90.0),
            "total-freedom-250gb-roam-beyond-50gb": (105.0, 100.0),
        }
        for ext_id, (regular, autopay) in expected.items():
            plan = by_id[ext_id]
            assert plan.regular_price_cad == regular
            assert plan.autopay_price_cad == autopay
            assert plan.autopay_discount_cad == 5
            assert plan.data_full_speed_gb == 250.0
            assert plan.network_technology == "5G+"
            assert plan.has_5g is True
            assert plan.includes_us is True and plan.includes_mexico is True
            assert plan.is_rankable is True
            assert plan.eligibility_restricted is not True

    def test_best_for_students_top5(self, session):
        _import_v1_dataset(session)
        res = rank_plans(session, STUDENTS, RankingContext(student_eligible=True), NOW, limit=5)
        ids = [r.plan.external_id for r in res.results]
        assert ids == [
            "total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer",
            "total-freedom-125gb-roam-beyond-5gb",
            "total-freedom-175gb-roam-beyond-10gb",
            "total-freedom-70gb-roam-beyond-1gb",
            "total-freedom-250gb-roam-beyond-10gb",
        ]
        scores = [r.final_score for r in res.results]
        assert scores == pytest.approx([77.58, 71.09, 70.69, 70.52, 68.66], abs=0.01)


# =====================================================================
# V1 customization: hard candidate-pool filters
# =====================================================================

_ALL_PRESETS = [OVERALL, STUDENTS, CHEAPEST, MOST_DATA, OFFERS]

# The frozen, approved Top-5 for each preset (external_ids), from the regression
# class above. Default customization must not disturb any of these.
_APPROVED_TOP5 = {
    OVERALL: [
        "total-freedom-175gb-roam-beyond-10gb",
        "total-freedom-125gb-roam-beyond-5gb",
        "total-freedom-250gb-roam-beyond-10gb",
        "total-freedom-70gb-roam-beyond-1gb",
        "total-freedom-250gb-roam-beyond-20gb",
    ],
    CHEAPEST: ["4014", "koodo-250mb-3g", "5156", "5157", "5159"],
    MOST_DATA: [
        "bell-ultra-unlimited-with-u-s-mexico-roaming",
        "bell-ultra-unlimited-with-international-roaming",
        "total-freedom-250gb-roam-beyond-10gb",
        "total-freedom-250gb-roam-beyond-20gb",
        "total-freedom-250gb-roam-beyond-30gb",
    ],
    OFFERS: [
        "bell-ultra-unlimited-with-u-s-mexico-roaming",
        "bell-select-100-gb-with-u-s-roaming",
        "total-freedom-70gb-roam-beyond-1gb",
        "total-freedom-125gb-roam-beyond-5gb",
        "total-freedom-175gb-roam-beyond-10gb",
    ],
}


class TestPassesFiltersUnit:
    """passes_filters() in isolation, on synthetic plans."""

    def test_all_default_filters_accept_everything(self):
        f = CustomFilters()
        assert not f.any_active
        assert passes_filters(_plan(), None, None, f) is True
        assert passes_filters(_plan(plan_type="prepaid"), 999.0, 0.0, f) is True

    # --- budget --------------------------------------------------
    def test_budget_uses_the_applicable_price_not_the_source_price(self):
        f = CustomFilters(max_monthly_price_cad=15)
        # a $159/12mo annual plan compares at its $13.25/mo equivalent
        assert passes_filters(_plan(), 13.25, 40.0, f) is True
        assert passes_filters(_plan(), 15.0, 5.0, f) is True
        assert passes_filters(_plan(), 15.01, 5.0, f) is False

    def test_budget_excludes_a_plan_with_no_applicable_price(self):
        assert passes_filters(_plan(), None, 10.0, CustomFilters(max_monthly_price_cad=50)) is False

    # --- minimum data ------------------------------------------
    def test_min_data_finite(self):
        f = CustomFilters(min_data_gb=50)
        assert passes_filters(_plan(), 40.0, 50.0, f) is True
        assert passes_filters(_plan(), 40.0, 49.9, f) is False

    def test_min_data_unlimited_satisfies_any_finite_minimum(self):
        assert passes_filters(_plan(), 60.0, "UNLIMITED", CustomFilters(min_data_gb=9999)) is True

    def test_min_data_known_zero_fails_any_positive_minimum(self):
        assert passes_filters(_plan(), 35.0, 0.0, CustomFilters(min_data_gb=1)) is False

    def test_min_data_unknown_fails_a_hard_requirement(self):
        assert passes_filters(_plan(), 35.0, None, CustomFilters(min_data_gb=1)) is False

    # --- plan type --------------------------------------------
    def test_plan_type_matches_only_the_verified_field(self):
        f = CustomFilters(plan_type="prepaid")
        assert passes_filters(_plan(plan_type="prepaid"), 20.0, 5.0, f) is True
        assert passes_filters(_plan(plan_type="postpaid"), 20.0, 5.0, f) is False
        assert passes_filters(_plan(plan_type=None), 20.0, 5.0, f) is False  # never inferred

    # --- 5G ---------------------------------------------------
    def test_require_5g_needs_explicit_5g_technology(self):
        f = CustomFilters(require_5g=True)
        assert passes_filters(_plan(network_technology="5G"), 40.0, 10.0, f) is True
        assert passes_filters(_plan(network_technology="5G+"), 40.0, 10.0, f) is True
        assert passes_filters(_plan(network_technology="4G LTE"), 40.0, 10.0, f) is False
        assert passes_filters(_plan(network_technology=None), 40.0, 10.0, f) is False  # unknown != 5G

    # --- Canada-US-Mexico ------------------------------------
    def test_require_can_us_mex_needs_both_verified_true(self):
        f = CustomFilters(require_can_us_mex=True)
        assert passes_filters(_plan(includes_us=True, includes_mexico=True), 40.0, 10.0, f) is True
        assert passes_filters(_plan(includes_us=True, includes_mexico=None), 40.0, 10.0, f) is False
        assert passes_filters(_plan(includes_us=True, includes_mexico=False), 40.0, 10.0, f) is False
        # international texting / generic roaming must NOT satisfy it
        assert passes_filters(
            _plan(international_text=True, international_roaming=True), 40.0, 10.0, f
        ) is False

    # --- international roaming -------------------------------
    def test_require_international_roaming_needs_verified_true(self):
        f = CustomFilters(require_international_roaming=True)
        assert passes_filters(_plan(international_roaming=True), 40.0, 10.0, f) is True
        assert passes_filters(_plan(international_roaming=None), 40.0, 10.0, f) is False
        assert passes_filters(_plan(international_roaming=False), 40.0, 10.0, f) is False


class TestCustomFiltersAgainstDataset:
    """rank_plans(filters=...) over the real approved V1 dataset."""

    def test_no_filters_matches_none_filters_and_the_approved_top5(self, session):
        _import_v1_dataset(session)
        for preset in [OVERALL, CHEAPEST, MOST_DATA, OFFERS]:
            a = rank_plans(session, preset, RankingContext(), NOW, limit=5)
            b = rank_plans(session, preset, RankingContext(), NOW, limit=5, filters=CustomFilters())
            ids_a = [r.plan.external_id for r in a.results]
            ids_b = [r.plan.external_id for r in b.results]
            assert ids_a == ids_b == _APPROVED_TOP5[preset]
            assert [r.final_score for r in a.results] == [r.final_score for r in b.results]
            assert a.candidate_count == b.candidate_count

    def test_max_budget(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(max_monthly_price_cad=20),
        )
        assert [r.plan.external_id for r in res.results] == ["4014", "5156", "koodo-250mb-3g"]
        assert all(r.price_used_cad is not None and r.price_used_cad <= 20 for r in res.results)
        assert res.pre_filter_count == 27

    def test_annual_monthly_equivalent_budget_comparison(self, session):
        _import_v1_dataset(session)
        # $15/mo budget must KEEP the $159/12mo Chatr plan (compares at $13.25/mo)
        res = rank_plans(
            session, CHEAPEST, RankingContext(), NOW, limit=5,
            filters=CustomFilters(max_monthly_price_cad=15),
        )
        ids = [r.plan.external_id for r in res.results]
        assert "4014" in ids
        annual = _by_id(res)["4014"]
        assert annual.price_used_cad == 13.25
        assert annual.commitment == {"upfront_cad": 159.0, "term_months": 12}  # disclosure preserved
        # $13/mo budget removes it (13.25 > 13) -> empty
        res2 = rank_plans(
            session, CHEAPEST, RankingContext(), NOW, limit=5,
            filters=CustomFilters(max_monthly_price_cad=13),
        )
        assert res2.results == []

    def test_min_data(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(min_data_gb=100),
        )
        for r in res.results:
            gb = data_gb(r.plan)
            assert gb == "UNLIMITED" or (gb is not None and gb >= 100)
        assert "total-freedom-70gb-roam-beyond-1gb" not in {r.plan.external_id for r in res.results}

    def test_genuinely_unlimited_satisfies_min_data(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, MOST_DATA, RankingContext(), NOW, limit=5,
            filters=CustomFilters(min_data_gb=500),
        )
        ids = [r.plan.external_id for r in res.results]
        # the two genuinely-unlimited Bell plans pass a 500GB minimum; finite ones don't
        assert ids[:2] == [
            "bell-ultra-unlimited-with-u-s-mexico-roaming",
            "bell-ultra-unlimited-with-international-roaming",
        ]
        assert all(
            data_gb(r.plan) == "UNLIMITED" for r in res.results
        )

    def test_plan_type_prepaid_and_postpaid_partition_the_pool(self, session):
        _import_v1_dataset(session)
        pre = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(plan_type="prepaid"),
        )
        post = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(plan_type="postpaid"),
        )
        assert all(r.plan.plan_type == "prepaid" for r in pre.results)
        assert all(r.plan.plan_type == "postpaid" for r in post.results)
        assert pre.candidate_count + post.candidate_count == pre.pre_filter_count == 27

    def test_require_5g(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(require_5g=True),
        )
        assert all(r.plan.network_technology in ("5G", "5G+") for r in res.results)
        assert res.candidate_count == 17  # +3 for the new 5G+ Freedom Roam Beyond tiers

    def test_require_can_us_mex(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(require_can_us_mex=True),
        )
        assert all(
            r.plan.includes_us is True and r.plan.includes_mexico is True for r in res.results
        )

    def test_require_international_roaming(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(require_international_roaming=True),
        )
        assert all(r.plan.international_roaming is True for r in res.results)

    def test_student_eligibility_with_budget_uses_the_student_price(self, session):
        _import_v1_dataset(session)
        # $46 budget + confirmed student eligibility -> the $45 student variant qualifies
        elig = rank_plans(
            session, STUDENTS, RankingContext(student_eligible=True), NOW, limit=50,
            filters=CustomFilters(max_monthly_price_cad=46),
        )
        assert "total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer" in {
            r.plan.external_id for r in elig.results
        }
        # same budget, not confirmed -> the restricted variant never enters the pool,
        # and the regular $55 plan is over budget
        not_elig = rank_plans(
            session, STUDENTS, RankingContext(student_eligible=False), NOW, limit=50,
            filters=CustomFilters(max_monthly_price_cad=46),
        )
        ids = {r.plan.external_id for r in not_elig.results}
        assert "total-freedom-175gb-roam-beyond-10gb-post-secondary-student-offer" not in ids
        assert "total-freedom-175gb-roam-beyond-10gb" not in ids

    def test_autopay_willingness_with_budget_uses_the_autopay_price(self, session):
        _import_v1_dataset(session)
        willing = rank_plans(
            session, OVERALL, RankingContext(autopay_willing=True), NOW, limit=50,
            filters=CustomFilters(max_monthly_price_cad=50),
        )
        # Freedom 175GB (regular $55, AutoPay-only tier $50) qualifies at $50 with AutoPay
        w = _by_id(willing).get("total-freedom-175gb-roam-beyond-10gb")
        assert w is not None and w.price_used_cad == 50.0
        not_willing = rank_plans(
            session, OVERALL, RankingContext(autopay_willing=False), NOW, limit=50,
            filters=CustomFilters(max_monthly_price_cad=50),
        )
        assert "total-freedom-175gb-roam-beyond-10gb" not in {
            r.plan.external_id for r in not_willing.results
        }

    def test_multiple_filters_combined(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=50,
            filters=CustomFilters(
                plan_type="postpaid", min_data_gb=100, require_can_us_mex=True
            ),
        )
        for r in res.results:
            assert r.plan.plan_type == "postpaid"
            gb = data_gb(r.plan)
            assert gb == "UNLIMITED" or gb >= 100
            assert r.plan.includes_us is True and r.plan.includes_mexico is True
        assert res.candidate_count == 8  # +3 for the new postpaid 250GB+US/MX Freedom tiers

    def test_impossible_filter_combination_returns_empty(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OVERALL, RankingContext(), NOW, limit=5,
            filters=CustomFilters(require_5g=True, max_monthly_price_cad=13),
        )
        assert res.results == []
        assert res.candidate_count == 0
        assert res.pre_filter_count == 27  # filters never silently relaxed

    def test_best_current_offers_still_requires_offer_over_zero(self, session):
        _import_v1_dataset(session)
        res = rank_plans(
            session, OFFERS, RankingContext(), NOW, limit=50,
            filters=CustomFilters(require_5g=True),
        )
        assert res.results
        assert all((r.offer_score or 0.0) > 0 for r in res.results)

    def test_municipality_still_has_no_effect_with_filters_active(self, session):
        _import_v1_dataset(session)
        out = []
        for muni in (None, "vancouver", "burnaby", "surrey"):
            res = rank_plans(
                session, OVERALL, RankingContext(municipality=muni), NOW, limit=10,
                filters=CustomFilters(require_5g=True, max_monthly_price_cad=60),
            )
            out.append([(r.plan.external_id, r.final_score) for r in res.results])
        assert all(o == out[0] for o in out)


class TestCustomizationApi:
    """The /api/rank query surface + the filters_applied response block."""

    def test_no_customization_params_keep_the_approved_top5(self, api):
        _import_v1_dataset(api.session)
        for preset, expected in _APPROVED_TOP5.items():
            body = api.client.get(f"/api/rank?preset={preset}").json()
            assert [r["external_id"] for r in body["results"]] == expected
            fa = body["filters_applied"]
            assert fa == {
                "max_monthly_price_cad": None, "min_data_gb": None, "plan_type": None,
                "require_5g": False, "require_can_us_mex": False,
                "require_international_roaming": False, "student_eligible": False,
                "autopay_willing": False, "any_active": False,
            }
            assert body["pre_filter_candidate_count"] == 27

    def test_filters_applied_echoes_the_active_customization(self, api):
        _import_v1_dataset(api.session)
        body = api.client.get(
            "/api/rank?preset=overall&max_monthly_price_cad=60&min_data_gb=50"
            "&plan_type=postpaid&require_5g=true&autopay_willing=true"
        ).json()
        fa = body["filters_applied"]
        assert fa["max_monthly_price_cad"] == 60
        assert fa["min_data_gb"] == 50
        assert fa["plan_type"] == "postpaid"
        assert fa["require_5g"] is True
        assert fa["autopay_willing"] is True
        assert fa["any_active"] is True
        assert body["results"]

    def test_plan_type_any_is_a_no_op(self, api):
        _import_v1_dataset(api.session)
        a = api.client.get("/api/rank?preset=overall").json()
        b = api.client.get("/api/rank?preset=overall&plan_type=any").json()
        assert [r["external_id"] for r in a["results"]] == [r["external_id"] for r in b["results"]]
        assert b["filters_applied"]["plan_type"] is None
        assert b["filters_applied"]["any_active"] is False

    def test_invalid_plan_type_is_a_400(self, api):
        _import_v1_dataset(api.session)
        assert api.client.get("/api/rank?preset=overall&plan_type=pay-as-you-go").status_code == 400

    def test_impossible_filters_return_200_with_an_empty_result_and_metadata(self, api):
        _import_v1_dataset(api.session)
        resp = api.client.get("/api/rank?preset=overall&max_monthly_price_cad=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"] == []
        assert body["candidate_count"] == 0
        assert body["pre_filter_candidate_count"] == 27  # enough metadata for an empty state
        assert body["filters_applied"]["max_monthly_price_cad"] == 5
        assert body["filters_applied"]["any_active"] is True

    def test_autopay_willing_is_exposed_and_defaults_false(self, api):
        _import_v1_dataset(api.session)
        assert api.client.get("/api/rank?preset=overall").json()["autopay_willing"] is False
        assert (
            api.client.get("/api/rank?preset=overall&autopay_willing=true").json()["autopay_willing"]
            is True
        )
