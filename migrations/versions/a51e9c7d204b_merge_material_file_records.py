"""Merge each material's file record into its stable material identity."""

import json

from alembic import context, op
import sqlalchemy as sa

revision = "a51e9c7d204b"
down_revision = "9e4b6c8d201a"
branch_labels = None
depends_on = None

PROJECT_FIELDS = (
    "goal", "current_level", "deadline", "daily_minutes", "weekly_days", "expected_outcome",
)
FILE_FIELDS = (
    "original_filename", "normalized_format", "mime_type", "size_bytes", "content_hash",
    "storage_object_key", "parser_name", "parser_version", "parse_status", "parse_job_id",
    "content_summary", "parsed_content_location", "source_metadata",
    "parse_error_code", "parse_error_message", "uploaded_at", "processed_at",
)
JSON_FIELDS = (
    ("plan_versions", "content"),
    ("replan_proposals", "proposed_content"),
    ("replan_proposals", "diff"),
    ("audit_events", "payload"),
)


def translate(value, mapping):
    if isinstance(value, list):
        return [translate(item, mapping) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "material_version_id":
            if type(item) is not int or item not in mapping or "material_id" in value:
                raise RuntimeError("Unmapped or ambiguous historical material reference")
            result["material_id"] = mapping[item]
        elif "material_version" in key:
            raise RuntimeError("Unsupported historical material reference key: " + key)
        else:
            result[key] = translate(item, mapping)
    return result


def upgrade() -> None:
    if context.is_offline_mode() or op.get_bind().dialect.name != "postgresql":
        raise RuntimeError("This migration requires online PostgreSQL and a backup")
    db = op.get_bind()
    db.execute(sa.text(
        "LOCK TABLE learning_projects, materials, material_versions, knowledge_node_sources, "
        "plan_versions, replan_proposals, audit_events IN ACCESS EXCLUSIVE MODE"
    ))
    checks = (
        ("SELECT count(*) FROM (SELECT m.id FROM materials m LEFT JOIN material_versions v "
         "ON v.material_id=m.id GROUP BY m.id HAVING count(v.id) <> 1) q",
         "Each material must have exactly one file record"),
        ("SELECT count(*) FROM material_versions WHERE version_number <> 1",
         "Review non-default material version numbers"),
        ("SELECT count(*) FROM materials WHERE enabled IS NOT TRUE OR deletion_started_at IS NOT NULL",
         "Finish disabled-material review and pending cleanup"),
        ("SELECT count(*) FROM material_versions WHERE parse_status IN ('QUEUED','PARSING')",
         "Finish active parsing"),
    )
    for query, message in checks:
        if db.execute(sa.text(query)).scalar_one():
            raise RuntimeError(message)
    inspector = sa.inspect(db)
    for table_name in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table_name):
            if fk["referred_table"] == "material_versions" and (
                table_name != "knowledge_node_sources"
                or fk["constrained_columns"] != ["material_version_id"]
            ):
                raise RuntimeError("Unexpected material file reference; review before migration")

    file_rows = db.execute(sa.text("SELECT id, material_id FROM material_versions"))
    mapping = {version_id: material_id for version_id, material_id in file_rows}

    # Validate all recognized JSON references before any schema changes.
    json_updates = []
    for table_name, column_name in JSON_FIELDS:
        for row in db.execute(sa.text(f"SELECT id, {column_name} FROM {table_name}")).mappings():
            original = row[column_name]
            updated = translate(original, mapping)
            if updated != original:
                json_updates.append((table_name, column_name, row["id"], updated))

    old_columns = {column["name"]: column for column in inspector.get_columns("material_versions")}
    for name in FILE_FIELDS:
        op.add_column("materials", sa.Column(name, old_columns[name]["type"], nullable=True))
    assignments = ", ".join(f"{name}=v.{name}" for name in FILE_FIELDS)
    db.execute(sa.text(f"UPDATE materials m SET {assignments} FROM material_versions v WHERE v.material_id=m.id"))
    for name in FILE_FIELDS:
        if not old_columns[name]["nullable"]:
            op.alter_column("materials", name, nullable=False)
    op.create_check_constraint("ck_materials_size_bytes", "materials", "size_bytes >= 0")
    op.create_check_constraint("ck_materials_format", "materials", "normalized_format = 'markdown'")
    op.create_check_constraint(
        "ck_materials_parse_status", "materials",
        "parse_status IN ('UPLOADED','QUEUED','PARSING','READY','FAILED')",
    )

    for fk in inspector.get_foreign_keys("knowledge_node_sources"):
        if fk["constrained_columns"] == ["material_version_id"]:
            constraint_name = fk["name"]
            if constraint_name is None:
                raise RuntimeError(
                    "Missing name for knowledge_node_sources.material_version_id foreign key"
                )
            op.drop_constraint(constraint_name, "knowledge_node_sources", type_="foreignkey")

    op.drop_index("ix_knowledge_node_sources_material_version_id", table_name="knowledge_node_sources")
    db.execute(sa.text(
        "UPDATE knowledge_node_sources s SET material_version_id=v.material_id "
        "FROM material_versions v WHERE s.material_version_id=v.id"
    ))
    op.alter_column("knowledge_node_sources", "material_version_id", new_column_name="material_id")
    op.create_foreign_key(
        "fk_knowledge_node_sources_material_id", "knowledge_node_sources",
        "materials", ["material_id"], ["id"],
    )
    op.create_index("ix_knowledge_node_sources_material_id", "knowledge_node_sources", ["material_id"])
    for table_name, column_name, row_id, value in json_updates:
        db.execute(sa.text(
            f"UPDATE {table_name} SET {column_name}=CAST(:value AS json) WHERE id=:id"
        ), {"value": json.dumps(value, ensure_ascii=False), "id": row_id})
    op.drop_table("material_versions")
    op.drop_column("materials", "enabled")
    op.drop_constraint("ck_learning_projects_daily_minutes", "learning_projects", type_="check")
    op.drop_constraint("ck_learning_projects_weekly_days", "learning_projects", type_="check")
    for name in PROJECT_FIELDS:
        op.drop_column("learning_projects", name)


def downgrade() -> None:
    raise RuntimeError(
        "This consolidation cannot reconstruct old identities or retired values. "
        "Restore the verified pre-upgrade database AND material-volume backups with the old image."
    )