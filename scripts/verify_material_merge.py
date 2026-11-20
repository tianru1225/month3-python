"""Synthetic migration and backup-restore checks; never production."""

import argparse
import base64
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from scripts.material_merge_data import (
    OLD_HEAD, NEW_HEAD, apply_or_verify, head, prepare, snapshot,
)

ROOT = Path("/work/materials")
MANIFEST = Path("/work/manifest.json")


def seed_database(engine, config):
    assert not inspect(engine).get_table_names(), "Disposable database must be empty"
    assert not ROOT.exists(), "Use a new disposable work volume"
    command.upgrade(config, OLD_HEAD)
    content = b"# Notes\nKeep source\n"
    metadata = MetaData()
    names = (
        "users", "learning_projects", "materials", "material_versions",
        "project_material_bindings", "knowledge_nodes", "knowledge_node_sources",
        "learning_plans", "plan_versions",
    )
    tables = {name: Table(name, metadata, autoload_with=engine) for name in names}
    now = datetime.now(timezone.utc)
    file_values = dict(
        material_id=41, version_number=1, original_filename="notes.md",
        normalized_format="markdown", mime_type="text/markdown", size_bytes=len(content),
        content_hash=hashlib.sha256(content).hexdigest(), storage_object_key="11/" + "b" * 32 + ".md",
        parse_status="READY", uploaded_at=now, processed_at=now,
        parser_name="markdown-token-parser", parser_version="preserve-parser-version",
        parsed_content_location="parsed/41/71.md",
        source_metadata={"sources_path": "parsed/41/71.sources.json"},
    )
    with engine.begin() as connection:
        connection.execute(tables["users"].insert().values(
            id=11, username="migration-fixture", password_hash="not-for-login",
            status="ACTIVE", created_at=now,
        ))
        connection.execute(tables["learning_projects"].insert().values(
            id=21, user_id=11, name="Keep project", goal="Legacy custom goal",
            current_level="intermediate", deadline=date(2027, 1, 1),
            daily_minutes=30, weekly_days=5, expected_outcome="Legacy custom outcome",
            status="ACTIVE", created_at=now, updated_at=now, deleted_at=now,
        ))
        connection.execute(tables["materials"].insert().values(
            id=41, user_id=11, name="Keep material", enabled=True, created_at=now, updated_at=now,
        ))
        connection.execute(tables["material_versions"].insert().values(id=71, **file_values))
        connection.execute(tables["project_material_bindings"].insert().values(
            id=81, project_id=21, material_id=41, bound_at=now, unbound_at=now,
        ))
        connection.execute(tables["knowledge_nodes"].insert().values(
            id=91, project_id=21, title="Keep node", description="Keep source",
            difficulty=1, status="ACTIVE", created_at=now, updated_at=now,
        ))
        connection.execute(tables["knowledge_node_sources"].insert().values(
            id=101, node_id=91, material_version_id=71, block_index=0,
            line_start=1, line_end=2, section_path=["Notes"], created_at=now,
        ))
        connection.execute(tables["learning_plans"].insert().values(
            id=111, project_id=21, name="Keep plan", created_at=now, updated_at=now,
        ))
        connection.execute(tables["plan_versions"].insert().values(
            id=121, plan_id=111, version_number=1, status="DRAFT", goal="Keep plan goal",
            content={"title": "Keep content", "source_materials": [{"material_version_id": 71}]}, source_kind="MANUAL",
            created_at=now, is_current=False,
        ))

    original = ROOT / file_values["storage_object_key"]
    original.parent.mkdir(parents=True)
    original.write_bytes(content)
    parsed = ROOT / "parsed/41/71.md"
    parsed.parent.mkdir(parents=True)
    parsed.write_bytes(content)
    parsed.with_suffix(".sources.json").write_text(json.dumps({
        "material_version_id": 71, "normalized_format": "markdown",
        "parser_version": "preserve-parser-version",
        "blocks": [{"text": "# Notes\nKeep source\n",
                    "source": {"line_start": 1, "line_end": 2, "section_path": ["Notes"]}}],
    }), encoding="utf-8")
    prepare(engine, ROOT, MANIFEST)
    print("MATERIAL_MERGE_SEEDED")


def exercise(engine, config):
    assert head(engine) == OLD_HEAD
    cases = [
        ("UPDATE material_versions SET version_number=2 WHERE id=71",
         "UPDATE material_versions SET version_number=1 WHERE id=71"),
        ("UPDATE materials SET enabled=false WHERE id=41",
         "UPDATE materials SET enabled=true WHERE id=41"),
        ("UPDATE materials SET deletion_started_at=CURRENT_TIMESTAMP WHERE id=41",
         "UPDATE materials SET deletion_started_at=NULL WHERE id=41"),
        ("UPDATE material_versions SET parse_status='QUEUED' WHERE id=71",
         "UPDATE material_versions SET parse_status='READY' WHERE id=71"),
        ("INSERT INTO materials(id,user_id,name,enabled) VALUES(42,11,'No file',true)",
         "DELETE FROM materials WHERE id=42"),
        ("INSERT INTO material_versions SELECT (jsonb_populate_record(NULL::material_versions, "
         "to_jsonb(v) || '{\"id\":72,\"version_number\":2}'::jsonb)).* "
         "FROM material_versions v WHERE id=71",
         "DELETE FROM material_versions WHERE id=72"),
    ]
    for change, undo in cases:
        with engine.begin() as db:
            db.exec_driver_sql(change)
        try:
            try:
                command.upgrade(config, NEW_HEAD)
            except RuntimeError:
                pass  # Expected refusal; the transaction must leave the old head intact.
            else:
                raise AssertionError("Unsafe input was accepted")
            assert head(engine) == OLD_HEAD
            assert inspect(engine).has_table("material_versions")
        finally:
            # Only synthetic fixtures in the isolated test database.
            with engine.begin() as db:
                db.execute(text(undo))
    source_path = ROOT / "parsed/41/71.sources.json"
    original = source_path.read_bytes()
    source_path.write_text('{"material_version_id": 999}', encoding="utf-8")
    try:
        try:
            prepare(engine, ROOT, Path("/work/invalid-manifest.json"))
        except RuntimeError:
            pass
        else:
            raise AssertionError("Invalid source identity was accepted")
    finally:
        source_path.write_bytes(original)
    assert snapshot(engine) == json.loads(MANIFEST.read_text())["before"]
    command.upgrade(config, NEW_HEAD)
    apply_or_verify(engine, ROOT, MANIFEST, True)
    apply_or_verify(engine, ROOT, MANIFEST, True)  # Interrupted maintenance can resume safely.
    assert not inspect(engine).has_table("material_versions")
    with engine.connect() as db:
        assert db.execute(text("SELECT material_id FROM knowledge_node_sources WHERE id=101")).scalar_one() == 41
        row = db.execute(text("SELECT id, version_number, goal, content FROM plan_versions WHERE id=121")).one()
        assert row.id == 121 and row.version_number == 1 and row.goal == "Keep plan goal"
        assert row.content == {"title": "Keep content", "source_materials": [{"material_id": 41}]}
    source_map = json.loads(source_path.read_text())
    assert source_map["material_id"] == 41 and "material_version_id" not in source_map
    try:
        with engine.begin() as db:
            db.execute(text("UPDATE knowledge_node_sources SET material_id=999 WHERE id=101"))
    except IntegrityError as error:
        assert getattr(error.orig, "sqlstate", None) == "23503"
    else:
        raise AssertionError("Source foreign key was lost")
    try:
        command.downgrade(config, OLD_HEAD)
    except RuntimeError as error:
        assert "Restore" in str(error)
    else:
        raise AssertionError("Unsafe downgrade was accepted")
    assert head(engine) == NEW_HEAD
    command.check(config)
    print("MATERIAL_MERGE_EXERCISE_OK")


def verify_restored(engine):
    data = json.loads(MANIFEST.read_text())
    assert head(engine) == OLD_HEAD
    assert snapshot(engine) == data["before"]
    for item in data["files"]:
        content = (ROOT / item["path"]).read_bytes()
        if "hash" in item:
            assert hashlib.sha256(content).hexdigest() == item["hash"]
        else:
            assert content == base64.b64decode(item["before"])
    print("MATERIAL_MERGE_BACKUP_RESTORE_OK")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "exercise", "verify-restored"))
    args = parser.parse_args()
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "schema_cleanup_check":
        raise RuntimeError("Only disposable schema_cleanup_check PostgreSQL is allowed")
    engine = create_engine(url)
    config = Config("alembic.ini")
    try:
        if args.action == "seed":
            seed_database(engine, config)
        elif args.action == "exercise":
            exercise(engine, config)
        else:
            verify_restored(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()