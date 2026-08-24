"""add materials and material versions

Revision ID: d125b3c4d5e6
Revises: d122a6f7b8c9
Create Date: 2026-08-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "d125b3c4d5e6"
down_revision = "d122a6f7b8c9"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_materials_id", "materials", ["id"], unique=False)
    op.create_index(
        "ix_materials_user_id",
        "materials",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "material_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "original_filename",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "normalized_format",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "storage_object_key",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column("parser_name", sa.String(length=80), nullable=True),
        sa.Column("parser_version", sa.String(length=40), nullable=True),
        sa.Column(
            "parse_status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'UPLOADED'"),
        ),
        sa.Column("content_summary", sa.Text(), nullable=True),
        sa.Column(
            "parsed_content_location",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column("source_metadata", sa.JSON(), nullable=True),
        sa.Column("parse_error_code", sa.String(length=80), nullable=True),
        sa.Column("parse_error_message", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "version_number >= 1",
            name="ck_material_versions_version_number",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name="ck_material_versions_size_bytes",
        ),
        sa.CheckConstraint(
            "normalized_format IN ('markdown','txt','text_pdf')",
            name="ck_material_versions_format",
        ),
        sa.CheckConstraint(
            "parse_status IN ('UPLOADED','QUEUED','PARSING','READY','FAILED')",
            name="ck_material_versions_parse_status",
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "material_id",
            "version_number",
            name="uq_material_versions_material_version",
        ),
    )
    op.create_index(
        "ix_material_versions_id",
        "material_versions",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_material_versions_material_id",
        "material_versions",
        ["material_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_material_versions_material_id",
        table_name="material_versions",
    )
    op.drop_index("ix_material_versions_id", table_name="material_versions")
    op.drop_table("material_versions")
    op.drop_index("ix_materials_user_id", table_name="materials")
    op.drop_index("ix_materials_id", table_name="materials")
    op.drop_table("materials")
