"""add material parse job id

Revision ID: d130f5a6b7c8
Revises: d129e4f6a7b8
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "d130f5a6b7c8"
down_revision = "d129e4f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "material_versions",
        sa.Column("parse_job_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("material_versions", "parse_job_id")
