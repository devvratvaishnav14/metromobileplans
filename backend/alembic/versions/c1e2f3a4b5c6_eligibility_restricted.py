"""restricted-eligibility flag (partner / employer / exclusive offers)

Revision ID: c1e2f3a4b5c6
Revises: b0a9a6beed72
Create Date: 2026-09-09 18:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c1e2f3a4b5c6'
down_revision: str | None = 'b0a9a6beed72'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('eligibility_restricted', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('eligibility_conditions', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_column('eligibility_conditions')
        batch_op.drop_column('eligibility_restricted')
