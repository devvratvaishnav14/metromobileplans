"""WhistleOut trusted_secondary adapter + multi-provider secondary pipeline."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from metromobile.models import Plan, Provider, RefreshRun
from metromobile.pipeline import run_refresh, run_secondary_refresh
from metromobile.providers.whistleout import WhistleOutAdapter
from metromobile.serializers import build_plans_response

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
WIDGET = FIXTURES / "whistleout" / "popular_plans_widget.html"
CHATR = FIXTURES / "chatr" / "plans_page.html"


def _parsed():
    return WhistleOutAdapter().parse(WIDGET.read_bytes())


def test_parses_the_popular_plans_widget():
    plans = _parsed()
    assert len(plans) >= 5
    providers = {p.attributes["_provider"]["slug"] for p in plans}
    # carriers we can't fetch directly show up here
    assert {"bell", "public-mobile", "fido"} <= providers


def test_secondary_fields_are_extracted_conservatively():
    by_slug: dict[str, list] = {}
    for p in _parsed():
        by_slug.setdefault(p.attributes["_provider"]["slug"], []).append(p)

    pm = by_slug["public-mobile"][0]
    assert pm.plan_type == "prepaid"
    assert pm.data_total_gb == 50.0
    assert pm.monthly_price_cad == 35.0
    assert pm.promo_conditions and "Public Points" in pm.promo_conditions
    assert pm.attributes["_source_url"].startswith("https://www.whistleout.ca/CellPhones/")

    bell = by_slug["bell"]
    assert any(b.contract_length_months == 24 for b in bell)  # both contract options captured
    assert all(b.data_unlimited is True for b in bell)
    assert all(b.throttle_speed == "512 Kbps" for b in bell)


def test_raises_if_widget_markup_changes():
    import pytest

    from metromobile.providers.base import ParseError

    with pytest.raises(ParseError):
        WhistleOutAdapter().parse(b"<html><body>no table here</body></html>")


def test_secondary_refresh_stores_per_provider_never_rankable(session):
    outcome = run_secondary_refresh("whistleout", session, fixture_path=WIDGET)
    assert outcome.status == "success"
    assert outcome.plans_valid == 0            # trusted_secondary is never rankable alone
    assert outcome.plans_flagged == outcome.plans_upserted

    plans = session.query(Plan).all()
    assert {p.source_mode for p in plans} == {"trusted_secondary"}
    assert {p.verification_status for p in plans} == {"secondary_confirmed"}
    assert all(p.confidence <= 0.6 for p in plans)
    # a real Provider row per carrier, tagged trusted_secondary
    slugs = {pr.slug for pr in session.query(Provider).all()}
    assert {"bell", "public-mobile", "fido"} <= slugs
    assert session.query(RefreshRun).one().source_mode == "trusted_secondary"


def test_secondary_does_not_downgrade_or_disturb_official_chatr(session):
    run_refresh("chatr", session, fixture_path=CHATR)              # official
    run_secondary_refresh("whistleout", session, fixture_path=WIDGET)  # secondary (also has a chatr row)

    chatr_provider = session.get(Provider, "chatr")
    assert chatr_provider.default_source_mode == "official_automated"  # not downgraded

    official = [p for p in session.query(Plan).filter_by(provider_slug="chatr").all()
                if p.source_mode == "official_automated"]
    secondary = [p for p in session.query(Plan).filter_by(provider_slug="chatr").all()
                 if p.source_mode == "trusted_secondary"]
    assert len(official) == 7 and all(p.verification_status == "verified" or p.verification_status == "provisional" for p in official)
    assert len(secondary) >= 1 and all(p.is_rankable is False for p in secondary)

    resp = build_plans_response(session, "vancouver", dt.datetime.now(dt.timezone.utc))
    assert resp.meta.source_mode_counts["official_automated"] == 7
    assert resp.meta.source_mode_counts["trusted_secondary"] >= 5
    assert resp.meta.rankable_count == 6      # only the official Chatr plans
