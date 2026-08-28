"""restrict material formats to markdown

Revision ID: d127c4d5e6f7
Revises: d125b3c4d5e6
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "d127c4d5e6f7"
down_revision = "d125b3c4d5e6"

branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    legacy_record = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM material_versions
            WHERE normalized_format <> 'markdown'
            LIMIT 1
            """
        )
    ).first()
    if legacy_record is not None:
        raise RuntimeError(
            "cannot restrict material formats while legacy records exist"
        )

    op.drop_constraint(
        "ck_material_versions_format",
        "material_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_material_versions_format",
        "material_versions",
        "normalized_format = 'markdown'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_material_versions_format",
        "material_versions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_material_versions_format",
        "material_versions",
        "normalized_format IN ('markdown','txt','text_pdf')",
    )
