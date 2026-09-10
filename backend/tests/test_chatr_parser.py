"""The parser is pinned to a saved snapshot of chatrwireless.com/plans.

If Chatr changes its page structure the snapshot test fails loudly (rather than
the pipeline silently emitting empty or wrong plans), which is the signal to
re-capture the fixture and re-check the mapping.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from metromobile.providers.base import ParseError
from metromobile.providers.chatr import ChatrAdapter

from pathlib import Path
FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _normalized(html: bytes):
    plans = ChatrAdapter().parse(html)
    return {p.external_id: p for p in plans}


def test_extracts_all_seven_current_plans(chatr_html):
    plans = _normalized(chatr_html)
    assert set(plans) == {"5156", "5157", "5159", "5192", "5193", "4014", "618"}


def test_known_values_are_faithful_to_the_source(chatr_html):
    p = _normalized(chatr_html)

    x = p["5193"]
    assert x.plan_name == "$35 Canada-Wide Talk & International Text 25GB"
    assert x.monthly_price_cad == 35.0
    assert x.regular_price_cad == 35.0
    assert x.promo_price_cad is None          # "OUR BEST DEAL" is a badge, not a discount
    assert x.price_period == "monthly"
    assert x.data_base_gb == 25.0
    assert x.data_bonus_gb == 5.0
    # unlimited-throttled: NO finite total cap; 30 GB is the full-speed bucket
    assert x.data_total_gb is None
    assert x.data_full_speed_gb == 30.0
    assert x.data_unlimited is True
    assert x.data_unlimited_is_full_speed is False
    assert x.data_hard_cap is False
    assert x.has_5g is False                  # "25GB" must not be misread as 5G
    assert x.network_speed_tier == "4G speeds up to 150Mbps"
    assert x.network_technology == "4G"
    assert x.max_download_mbps == 150.0
    assert x.plan_type == "prepaid"
    assert x.contract_required is False       # "no contracts"
    assert x.canada_wide_calling is True
    assert x.unlimited_text is True
    assert x.includes_us is False             # US texting only; no US calling/data
    assert x.student_plan is None             # source is silent -> unknown, not False

    # annual plan: keep the real number, never synthesize a monthly rate
    assert p["4014"].price_cad == 159.0
    assert p["4014"].price_period == "annual"
    assert p["4014"].term_months == 12
    assert p["4014"].monthly_price_cad is None

    # 400-minute talk+text plan: not unlimited talk, no data -> unknowns stay None
    assert p["618"].canada_wide_calling is False
    assert p["618"].data_total_gb is None
    assert p["618"].data_unlimited is None


def test_matches_committed_snapshot(chatr_html):
    expected = json.loads((FIXTURES / "chatr" / "expected_normalized.json").read_text())
    got = sorted(
        (
            {k: v for k, v in dataclasses.asdict(p).items() if k != "attributes"}
            for p in ChatrAdapter().parse(chatr_html)
        ),
        key=lambda d: d["external_id"],
    )
    assert got == sorted(expected, key=lambda d: d["external_id"])


def test_raises_when_app_state_script_is_gone():
    with pytest.raises(ParseError):
        ChatrAdapter().parse(b"<html><body>no state here</body></html>")


def test_raises_when_state_has_no_plans():
    html = b'<script id="app-root-state" type="application/json">{"foo": {"bar": 1}}</script>'
    with pytest.raises(ParseError):
        ChatrAdapter().parse(html)
