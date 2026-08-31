"""add knowledge nodes, prerequisites and sources"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d132f6a7b8c9"
down_revision: Union[str, None] = "d130f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(title) BETWEEN 1 AND 160",
            name="ck_knowledge_nodes_title",
        ),
        sa.CheckConstraint(
            "length(description) BETWEEN 1 AND 5000",
            name="ck_knowledge_nodes_description",
        ),
        sa.CheckConstraint(
            "difficulty BETWEEN 1 AND 5",
            name="ck_knowledge_nodes_difficulty",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','ARCHIVED')",
            name="ck_knowledge_nodes_status",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["learning_projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_nodes_id", "knowledge_nodes", ["id"], unique=False)
    op.create_index(
        "ix_knowledge_nodes_project_id",
        "knowledge_nodes",
        ["project_id"],
        unique=False,
    )

    op.create_table(
        "knowledge_node_prerequisites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("prerequisite_node_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "node_id <> prerequisite_node_id",
            name="ck_knowledge_node_prerequisites_not_self",
        ),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"]),
        sa.ForeignKeyConstraint(["prerequisite_node_id"], ["knowledge_nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "node_id",
            "prerequisite_node_id",
            name="uq_knowledge_node_prerequisites_edge",
        ),
    )
    op.create_index(
        "ix_knowledge_node_prerequisites_id",
        "knowledge_node_prerequisites",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_node_prerequisites_node_id",
        "knowledge_node_prerequisites",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_node_prerequisites_prerequisite_node_id",
        "knowledge_node_prerequisites",
        ["prerequisite_node_id"],
        unique=False,
    )

    op.create_table(
        "knowledge_node_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=False),
        sa.Column("material_version_id", sa.Integer(), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("section_path", sa.JSON(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("quote_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "block_index >= 0",
            name="ck_knowledge_node_sources_block_index",
        ),
        sa.CheckConstraint(
            "line_start >= 1 AND line_end >= line_start",
            name="ck_knowledge_node_sources_line_range",
        ),
        sa.ForeignKeyConstraint(["node_id"], ["knowledge_nodes.id"]),
        sa.ForeignKeyConstraint(["material_version_id"], ["material_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_knowledge_node_sources_id",
        "knowledge_node_sources",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_node_sources_node_id",
        "knowledge_node_sources",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_node_sources_material_version_id",
        "knowledge_node_sources",
        ["material_version_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_node_sources_material_version_id",
        table_name="knowledge_node_sources",
    )
    op.drop_index(
        "ix_knowledge_node_sources_node_id", table_name="knowledge_node_sources"
    )
    op.drop_index("ix_knowledge_node_sources_id", table_name="knowledge_node_sources")
    op.drop_table("knowledge_node_sources")
    op.drop_index(
        "ix_knowledge_node_prerequisites_prerequisite_node_id",
        table_name="knowledge_node_prerequisites",
    )
    op.drop_index(
        "ix_knowledge_node_prerequisites_node_id",
        table_name="knowledge_node_prerequisites",
    )
    op.drop_index(
        "ix_knowledge_node_prerequisites_id",
        table_name="knowledge_node_prerequisites",
    )
    op.drop_table("knowledge_node_prerequisites")
    op.drop_index("ix_knowledge_nodes_project_id", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_id", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
