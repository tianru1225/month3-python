"""Add a project deletion marker without removing learning data."""

from alembic import op
import sqlalchemy as sa

revision = "7c2e9a4b6d10"
down_revision = "d139f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "learning_projects",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("learning_projects", "deleted_at")