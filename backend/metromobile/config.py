"""Runtime configuration. Everything has a working default so `metromobile` runs
with no .env at all; PostgreSQL and tighter freshness windows are opt-in."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

_LOCAL_DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="METROMOBILE_",
        env_file=str(BACKEND_DIR / ".env"),
        extra="ignore",
    )

    # SQLite by default (local dev). In production set a PostgreSQL URL via
    # METROMOBILE_DATABASE_URL, or the plain DATABASE_URL that managed hosts
    # (Render, etc.) inject automatically. A `postgres://` / `postgresql://`
    # scheme is upgraded to the psycopg (v3) driver.
    database_url: str = Field(
        default=f"sqlite:///{BACKEND_DIR / 'metromobile.db'}",
        validation_alias=AliasChoices("METROMOBILE_DATABASE_URL", "DATABASE_URL"),
    )

    http_user_agent: str = (
        "metro-mobile-plans/1.0 (plan comparison bot; contact: set METROMOBILE_HTTP_USER_AGENT)"
    )
    http_timeout_seconds: float = 20.0

    # --- Freshness policy, per source mode -------------------------------
    # Verified <= fresh => normal; <= stale threshold => warning ("aging");
    # older => stale (flagged, dropped from the "current" count, NOT rankable).

    # official_automated: refreshed by a scheduler, so windows are short.
    fresh_hours: float = 6.0
    aging_hours: float = 24.0

    # official_manual: a person verified it against the official page. A capture is
    # "current" for a week, "aging" past that, stale + ranking-ineligible past two
    # weeks. Production raises these via METROMOBILE_MANUAL_* env vars to match its
    # actual (less frequent) manual re-verification cadence.
    manual_fresh_hours: float = 168.0     # 7 days
    manual_reverify_hours: float = 336.0  # 14 days

    # trusted_secondary: reputable third party. Stricter still, and (below) never
    # "verified" or rankable on its own.
    secondary_fresh_hours: float = 12.0
    secondary_reverify_hours: float = 36.0

    # trusted_secondary policy
    secondary_confidence_cap: float = 0.6
    # Secondary-only records never enter ranked results unless this is flipped on
    # (an explicit policy decision) or an official cross-check exists for the plan.
    secondary_ranking_allowed: bool = False

    # Browser origin(s) allowed to call the API. Comma-separated for more than
    # one (e.g. a Vercel production + preview domain). The local dev origins are
    # always allowed on top of whatever is configured.
    frontend_origin: str = _LOCAL_DEV_ORIGINS[0]

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, v: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def allowed_origins(self) -> list[str]:
        configured = [o.strip().rstrip("/") for o in self.frontend_origin.split(",") if o.strip()]
        # de-duplicate, preserve order, always keep local dev working
        return list(dict.fromkeys([*configured, *_LOCAL_DEV_ORIGINS]))


@lru_cache
def get_settings() -> Settings:
    return Settings()
