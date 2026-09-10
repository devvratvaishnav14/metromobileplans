"""Freshness policy. The product never says data is "live" -- it says how long
ago each plan was last verified. Windows depend on the source mode:

    official_automated : fresh_hours / aging_hours          (scheduler-refreshed)
    official_manual    : manual_fresh_hours / manual_reverify_hours   (strict)
    trusted_secondary  : secondary_fresh_hours / secondary_reverify_hours (stricter)

Past the stale threshold a plan is flagged, dropped from the "current" count,
and loses ranking eligibility until it is re-verified.
"""

from __future__ import annotations

import datetime as dt

from .config import Settings, get_settings

# ordered best -> worst
FRESH = "fresh"
AGING = "aging"
STALE = "stale"

OFFICIAL_AUTOMATED = "official_automated"
OFFICIAL_MANUAL = "official_manual"
TRUSTED_SECONDARY = "trusted_secondary"


def _windows(source_mode: str, settings: Settings) -> tuple[float, float]:
    if source_mode == OFFICIAL_MANUAL:
        return settings.manual_fresh_hours, settings.manual_reverify_hours
    if source_mode == TRUSTED_SECONDARY:
        return settings.secondary_fresh_hours, settings.secondary_reverify_hours
    return settings.fresh_hours, settings.aging_hours


def freshness_state(
    last_verified_at: dt.datetime,
    *,
    source_mode: str = OFFICIAL_AUTOMATED,
    now: dt.datetime | None = None,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings()
    now = now or dt.datetime.now(dt.timezone.utc)
    if last_verified_at.tzinfo is None:
        last_verified_at = last_verified_at.replace(tzinfo=dt.timezone.utc)
    age_hours = (now - last_verified_at).total_seconds() / 3600.0
    fresh_h, stale_h = _windows(source_mode, settings)
    if age_hours <= fresh_h:
        return FRESH
    if age_hours <= stale_h:
        return AGING
    return STALE


def humanize_age(since: dt.datetime, *, now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.timezone.utc)
    if since.tzinfo is None:
        since = since.replace(tzinfo=dt.timezone.utc)
    seconds = max(0, int((now - since).total_seconds()))
    if seconds < 90:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"
