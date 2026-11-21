"""Remove unused states, duplicate material time and derived quote hash."""

from alembic import context, op
import sqlalchemy as sa

revision = "c62f0a8e315d"
down_revision = "a51e9c7d204b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode() or op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("This migration requires online PostgreSQL and a backup")
    db = op.get_bind()
    db.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    db.execute(sa.text(
        "LOCK TABLE learning_projects, knowledge_nodes, materials, "
        "knowledge_node_sources IN ACCESS EXCLUSIVE MODE"
    ))
    checks = (
        ("SELECT count(*) FROM learning_projects WHERE status <> 'ACTIVE'",
         "Review non-default project states before removing status"),
        ("SELECT count(*) FROM knowledge_nodes WHERE status <> 'DRAFT'",
         "Review non-default knowledge states before removing status"),
    )
    for query, message in checks:
        if db.execute(sa.text(query)).scalar_one():
            raise RuntimeError(message)
    op.drop_constraint("ck_learning_projects_status", "learning_projects", type_="check")
    op.drop_constraint("ck_knowledge_nodes_status", "knowledge_nodes", type_="check")
    op.drop_column("learning_projects", "status")
    op.drop_column("knowledge_nodes", "status")
    op.drop_column("materials", "created_at")
    op.drop_column("knowledge_node_sources", "quote_hash")


def downgrade() -> None:
    raise RuntimeError(
        "Restore the pre-upgrade database backup and matching application image; "
        "removed historical timestamps cannot be reconstructed."
    )