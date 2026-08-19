"""remove email from users

Revision ID: 7c1a8796e34b
Revises: b7e4c2a91f03
Create Date: 2026-08-19

Downgrade 说明：email 列只能以 nullable=True 的形式恢复。
原有的 NOT NULL 约束和历史邮箱值无法还原，本次迁移不可逆。

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "7c1a8796e34b"
down_revision = "b7e4c2a91f03"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)