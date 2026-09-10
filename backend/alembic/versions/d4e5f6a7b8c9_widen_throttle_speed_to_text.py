"""widen plans.throttle_speed to Text

VARCHAR(64) was too short for the free-text, network-dependent throttle policy
strings (e.g. Freedom's ~126-char sentence). SQLite ignores VARCHAR length so
this only surfaced on PostgreSQL as StringDataRightTruncation.

Revision ID: d4e5f6a7b8c9
Revises: c1e2f3a4b5c6
Create Date: 2026-09-10 20:35:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c1e2f3a4b5c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.alter_column(
            'throttle_speed',
            existing_type=sa.String(length=64),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.alter_column(
            'throttle_speed',
            existing_type=sa.Text(),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
