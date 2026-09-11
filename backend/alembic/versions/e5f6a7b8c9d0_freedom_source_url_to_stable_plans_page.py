"""point Freedom Mobile's source_url at the stable top-level plans page

The stored Freedom source_url used the deeper
``https://shop.freedommobile.ca/en-CA/plans/bring-your-own-phone`` route. That
path no longer resolves to a usable public page — the client-rendered shop app
renders "Sorry, something went wrong" for it. The stable, current official
Freedom Mobile plans page is ``https://shop.freedommobile.ca/en-CA/plans``
(``www.freedommobile.ca/en-CA/plans`` redirects there). Freedom publishes no
stable plan-specific URLs, so every Freedom plan points at that one page.

This repairs only the provenance pointer used by "View official source". No
plan facts, pricing, data, roaming, student flags, verification status,
last_verified_at, or source_mode are touched. Historical rows
(plan_verification_events.source_url, raw_documents.official_source_url) are
left intact as immutable evidence. Idempotent: a second run matches no rows.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-11 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# These URLs contain no quote characters, so they are safe to inline as SQL
# literals — which also keeps `alembic upgrade --sql` (offline) output correct.
_OLD_URL = "https://shop.freedommobile.ca/en-CA/plans/bring-your-own-phone"
_NEW_URL = "https://shop.freedommobile.ca/en-CA/plans"

# (table, column) pairs holding the *current* Freedom source pointer.
_TARGETS = (("plans", "source_url"), ("sources", "url"))


def _swap(old: str, new: str) -> None:
    conn = op.get_bind()
    for table, column in _TARGETS:
        conn.execute(
            sa.text(
                f"UPDATE {table} SET {column} = '{new}' "
                f"WHERE provider_slug = 'freedom-mobile' AND {column} = '{old}'"
            )
        )


def upgrade() -> None:
    _swap(_OLD_URL, _NEW_URL)


def downgrade() -> None:
    _swap(_NEW_URL, _OLD_URL)
