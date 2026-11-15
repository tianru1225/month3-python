"""Track incomplete permanent material cleanup."""

from alembic import op
import sqlalchemy as sa

revision = "9e4b6c8d201a"
down_revision = "7c2e9a4b6d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "materials",
        sa.Column("deletion_started_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    pending = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM materials WHERE deletion_started_at IS NOT NULL"
    )).scalar_one()
    if pending:
        raise RuntimeError("Finish pending material cleanup before downgrade")
    op.drop_column("materials", "deletion_started_at")