from __future__ import annotations

import datetime as dt

from metromobile.config import Settings
from metromobile.freshness import AGING, FRESH, STALE, freshness_state, humanize_age

S = Settings(fresh_hours=6, aging_hours=24)
NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=dt.timezone.utc)


def test_freshness_bands():
    assert freshness_state(NOW - dt.timedelta(hours=1), now=NOW, settings=S) == FRESH
    assert freshness_state(NOW - dt.timedelta(hours=12), now=NOW, settings=S) == AGING
    assert freshness_state(NOW - dt.timedelta(hours=30), now=NOW, settings=S) == STALE


def test_manual_and_secondary_windows_are_stricter_than_they_are_lenient():
    ms = Settings(
        manual_fresh_hours=24, manual_reverify_hours=72,
        secondary_fresh_hours=12, secondary_reverify_hours=36,
    )
    # manual: fresh < 24h, stale > 72h
    assert freshness_state(NOW - dt.timedelta(hours=10), source_mode="official_manual", now=NOW, settings=ms) == FRESH
    assert freshness_state(NOW - dt.timedelta(hours=48), source_mode="official_manual", now=NOW, settings=ms) == AGING
    assert freshness_state(NOW - dt.timedelta(hours=100), source_mode="official_manual", now=NOW, settings=ms) == STALE
    # secondary: stale even sooner
    assert freshness_state(NOW - dt.timedelta(hours=48), source_mode="trusted_secondary", now=NOW, settings=ms) == STALE


def test_naive_datetime_is_treated_as_utc():
    assert freshness_state(NOW.replace(tzinfo=None) - dt.timedelta(hours=1), now=NOW, settings=S) == FRESH


def test_humanize_age():
    assert humanize_age(NOW - dt.timedelta(seconds=30), now=NOW) == "just now"
    assert humanize_age(NOW - dt.timedelta(minutes=5), now=NOW) == "5 minutes ago"
    assert humanize_age(NOW - dt.timedelta(hours=3), now=NOW) == "3 hours ago"
    assert humanize_age(NOW - dt.timedelta(days=2), now=NOW) == "2 days ago"
