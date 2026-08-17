"""add user auth fields

Revision ID: b7e4c2a91f03
Revises: c50e4964d082
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "b7e4c2a91f03"
down_revision = "c50e4964d082"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="ACTIVE",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.execute(
        "UPDATE users "
        "SET password_hash = '!legacy-user-without-password', "
        "status = 'DISABLED' "
        "WHERE password_hash IS NULL"
    )

    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "users",
        "status",
        existing_type=sa.String(length=20),
        server_default=None,
    )
    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
    )
    op.create_check_constraint(
        "ck_users_status",
        "users",
        "status IN ('ACTIVE', 'DISABLED', 'LOCKED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_status", "users", type_="check")
    op.drop_column("users", "created_at")
    op.drop_column("users", "status")
    op.drop_column("users", "password_hash")
