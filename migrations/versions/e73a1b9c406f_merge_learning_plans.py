"""Merge plan identity and version into one plan per project.

Old version IDs become plan IDs. No task/evidence IDs are changed.
Ambiguous or retired historical data blocks migration instead of being discarded.
"""
from alembic import op
import sqlalchemy as sa

revision = "e73a1b9c406f"
down_revision = "c62f0a8e315d"
branch_labels = None
depends_on = None


def _require_safe(conn) -> None:
    checks = {
        "MULTIPLE_PLANS": """
            SELECT project_id FROM learning_plans GROUP BY project_id HAVING count(*) > 1
        """,
        "VERSION_COUNT": """
            SELECT p.id FROM learning_plans p LEFT JOIN plan_versions v ON v.plan_id=p.id
            GROUP BY p.id HAVING count(v.id) <> 1
        """,
        "RETIRED_VERSION": """
            SELECT id FROM plan_versions
            WHERE status='REJECTED' OR (status='PUBLISHED' AND NOT is_current)
        """,
        "DRAFT_HAS_HISTORY": """
            SELECT v.id FROM plan_versions v WHERE v.status='DRAFT' AND (
                EXISTS (SELECT 1 FROM learning_tasks t WHERE t.plan_version_id=v.id
                        AND t.status NOT IN ('DRAFT','READY'))
                OR EXISTS (SELECT 1 FROM evidence e WHERE e.plan_version_id=v.id)
                OR EXISTS (SELECT 1 FROM replan_proposals r WHERE r.base_plan_version_id=v.id)
            )
        """,
    }
    for code, sql in checks.items():
        ids = list(conn.execute(sa.text(sql)).scalars())
        if ids:
            raise RuntimeError(f"PLAN_MERGE_{code}: {ids}; preserve data and review before retry")


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("plan merge requires an online PostgreSQL connection")
    conn.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    conn.execute(sa.text(
        "LOCK TABLE learning_projects, learning_plans, plan_versions, learning_tasks, "
        "task_prerequisites, evidence, replan_proposals IN ACCESS EXCLUSIVE MODE"
    ))
    _require_safe(conn)
    op.create_table(
        "single_learning_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("provider_name", sa.String(80)),
        sa.Column("model_name", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["project_id"], ["learning_projects.id"]),
        sa.UniqueConstraint("project_id", name="uq_learning_plans_project"),
        sa.CheckConstraint(
            "provider_name IS NULL OR length(trim(provider_name)) BETWEEN 1 AND 80",
            name="ck_learning_plans_provider_name",
        ),
        sa.CheckConstraint(
            "model_name IS NULL OR length(trim(model_name)) BETWEEN 1 AND 160",
            name="ck_learning_plans_model_name",
        ),
        sa.CheckConstraint(
            "(provider_name IS NOT NULL "
            "AND model_name IS NOT NULL) OR "
            "(provider_name IS NULL AND model_name IS NULL)",
            name="ck_learning_plans_model_identity",
        ),
    )
    conn.execute(sa.text("""
        INSERT INTO single_learning_plans
            (id, project_id, content, provider_name, model_name,
             created_at, updated_at, locked_at)
        SELECT v.id, p.project_id, v.content,
               v.provider_name, v.model_name, v.created_at,
               greatest(p.updated_at, v.created_at), v.published_at
        FROM plan_versions v JOIN learning_plans p ON p.id=v.plan_id
    """))
    # Drop all affected foreign keys before replacing their referenced tables/columns.
    inspector = sa.inspect(conn)
    for table in ("evidence", "task_prerequisites", "learning_tasks", "replan_proposals"):
        for fk in inspector.get_foreign_keys(table):
            if fk["referred_table"] in ("learning_tasks", "plan_versions"):
                op.drop_constraint(fk["name"], table, type_="foreignkey")
    for name in ("uq_learning_tasks_id_plan_version", "uq_learning_tasks_version_position"):
        op.drop_constraint(name, "learning_tasks", type_="unique")
    renames = (
        ("learning_tasks", "plan_version_id", "plan_id"),
        ("task_prerequisites", "plan_version_id", "plan_id"),
        ("evidence", "plan_version_id", "plan_id"),
        ("replan_proposals", "base_plan_version_id", "base_plan_id"),
    )
    for table, old, new in renames:
        op.drop_index(f"ix_{table}_{old}", table_name=table)
        op.alter_column(table, old, new_column_name=new, existing_type=sa.Integer())
        op.create_index(f"ix_{table}_{new}", table, [new])
    op.drop_index("ix_learning_tasks_version_date_position", table_name="learning_tasks")
    op.create_index(
        "ix_learning_tasks_plan_date_position", "learning_tasks",
        ["plan_id", "scheduled_date", "position"],
    )
    op.drop_table("plan_versions")
    op.drop_table("learning_plans")
    op.rename_table("single_learning_plans", "learning_plans")
    op.create_index("ix_learning_plans_id", "learning_plans", ["id"])
    op.create_index("ix_learning_plans_project_id", "learning_plans", ["project_id"])
    op.create_unique_constraint(
        "uq_learning_tasks_id_plan", "learning_tasks", ["id", "plan_id"]
    )
    op.create_unique_constraint(
        "uq_learning_tasks_plan_position", "learning_tasks", ["plan_id", "position"]
    )
    op.create_foreign_key(
        "fk_learning_tasks_plan", "learning_tasks", "learning_plans", ["plan_id"], ["id"]
    )
    op.create_foreign_key(
        "fk_replan_proposals_plan", "replan_proposals", "learning_plans",
        ["base_plan_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_evidence_task_plan", "evidence", "learning_tasks",
        ["task_id", "plan_id"], ["id", "plan_id"],
    )
    for column, name in (
        ("task_id", "fk_task_prerequisites_task_plan"),
        ("prerequisite_task_id", "fk_task_prerequisites_prerequisite_plan"),
    ):
        op.create_foreign_key(
            name, "task_prerequisites", "learning_tasks",
            [column, "plan_id"], ["id", "plan_id"],
        )
    conn.execute(sa.text("""
        SELECT setval(
            pg_get_serial_sequence('learning_plans','id'),
            coalesce((SELECT max(id) FROM learning_plans),1),
            EXISTS (SELECT 1 FROM learning_plans)
        )
    """))


def downgrade() -> None:
    raise RuntimeError(
        "Removed plan/version metadata cannot be reconstructed. "
        "Restore the pre-migration dump with its matching application image."
    )