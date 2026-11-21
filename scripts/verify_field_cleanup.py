"""Read-only data manifests and an explicitly isolated PostgreSQL exercise."""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError

OLD_HEAD = "a51e9c7d204b"
NEW_HEAD = "c62f0a8e315d"
REMOVED = {
    "learning_projects": {"status"},
    "knowledge_nodes": {"status"},
    "materials": {"created_at"},
    "knowledge_node_sources": {"quote_hash"},
}


def head(engine: Engine) -> str:
    with engine.connect() as db:
        return str(db.execute(text("SELECT version_num FROM alembic_version")).scalar_one())


def snapshot(engine: Engine) -> dict:
    result = {}
    with engine.connect() as db:
        # Stable read view. All application writers must also be stopped for
        # production prepare -> migration -> verify.
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        quote = db.dialect.identifier_preparer.quote_identifier
        for name in sorted(inspect(db).get_table_names(schema="public")):
            if name == "alembic_version":
                continue
            rows = list(db.execute(
                text(f"SELECT to_jsonb(t) FROM public.{quote(name)} AS t")
            ).scalars())
            result[name] = sorted(
                rows, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False)
            )
    return result


def write_manifest(engine: Engine, path: Path) -> None:
    if head(engine) != OLD_HEAD:
        raise RuntimeError("prepare requires the pre-upgrade revision")
    with path.open("x", encoding="utf-8") as output:
        json.dump(
            {"revision": OLD_HEAD, "rows": snapshot(engine)},
            output, ensure_ascii=False, indent=2,
        )
    print("FIELD_CLEANUP_PREPARED")


def verify(engine: Engine, path: Path, *, restored: bool = False) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["revision"] == OLD_HEAD
    assert head(engine) == (OLD_HEAD if restored else NEW_HEAD)
    expected = manifest["rows"]
    if not restored:
        for name, fields in REMOVED.items():
            for row in expected[name]:
                for field in fields:
                    del row[field]
        for rows in expected.values():
            rows.sort(key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))
        inspector = inspect(engine)
        for name, fields in REMOVED.items():
            actual_columns = {item["name"] for item in inspector.get_columns(name)}
            assert not fields.intersection(actual_columns), name
    assert snapshot(engine) == expected, "Unexpected change to retained rows or fields"
    print("FIELD_CLEANUP_RESTORE_OK" if restored else "FIELD_CLEANUP_DATA_OK")


def seed(engine: Engine, config: Config, path: Path) -> None:
    assert not inspect(engine).get_table_names(schema="public"), "Use an empty test database"
    command.upgrade(config, OLD_HEAD)
    metadata = MetaData()
    names = (
        "users", "learning_projects", "materials", "project_material_bindings",
        "knowledge_nodes", "knowledge_node_sources", "learning_plans", "plan_versions",
    )
    tables = {name: Table(name, metadata, autoload_with=engine) for name in names}
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    uploaded = created + timedelta(seconds=17)
    with engine.begin() as db:
        db.execute(tables["users"].insert().values(
            id=11, username="field-cleanup-fixture", password_hash="not-for-login",
            status="ACTIVE", created_at=created,
        ))
        db.execute(tables["learning_projects"].insert().values(
            id=21, user_id=11, name="Keep deleted project", status="ACTIVE",
            created_at=created, updated_at=uploaded, deleted_at=uploaded,
        ))
        db.execute(tables["materials"].insert().values(
            id=41, user_id=11, name="Keep material", description="Keep description",
            created_at=created, updated_at=uploaded, uploaded_at=uploaded,
            original_filename="notes.md", normalized_format="markdown",
            mime_type="text/markdown", size_bytes=12, content_hash="a" * 64,
            storage_object_key="11/original.md", parse_status="FAILED",
            parse_job_id="keep-job", parse_error_code="KEEP_ERROR",
            parse_error_message="Keep error", parser_version="keep-parser",
            processed_at=uploaded,
        ))
        db.execute(tables["project_material_bindings"].insert().values(
            id=51, project_id=21, material_id=41, bound_at=created, unbound_at=uploaded,
        ))
        db.execute(tables["knowledge_nodes"].insert().values(
            id=61, project_id=21, title="Keep node", description="Keep knowledge",
            difficulty=2, status="DRAFT", created_at=created, updated_at=uploaded,
        ))
        db.execute(tables["knowledge_node_sources"].insert().values(
            id=71, node_id=61, material_id=41, block_index=0, line_start=1, line_end=2,
            section_path=["Notes"], quote="Keep quote", quote_hash="b" * 64,
            created_at=created,
        ))
        db.execute(tables["learning_plans"].insert().values(
            id=81, project_id=21, name="Keep plan", created_at=created, updated_at=uploaded,
        ))
        db.execute(tables["plan_versions"].insert().values(
            id=91, plan_id=81, version_number=1, status="DRAFT", goal="Keep goal",
            content={"material_id": 41, "knowledge_node_ids": [61]},
            source_kind="MANUAL", created_at=created, is_current=False,
        ))
    write_manifest(engine, path)


def exercise(engine: Engine, config: Config, path: Path) -> None:
    assert head(engine) == OLD_HEAD
    cases = (
        ("learning_projects", "PAUSED", "ACTIVE"),
        ("knowledge_nodes", "ARCHIVED", "DRAFT"),
    )
    for table_name, invalid, normal in cases:
        with engine.begin() as db:
            db.execute(text(f"UPDATE {table_name} SET status=:value"), {"value": invalid})
        before = snapshot(engine)
        try:
            command.upgrade(config, NEW_HEAD)
        except RuntimeError as error:
            assert "non-default" in str(error)
        else:
            raise AssertionError("Non-default state was silently discarded")
        assert head(engine) == OLD_HEAD
        assert snapshot(engine) == before, "Failed migration changed data"
        with engine.begin() as db:
            db.execute(text(f"UPDATE {table_name} SET status=:value"), {"value": normal})

    command.upgrade(config, NEW_HEAD)
    verify(engine, path)
    # Check a real remaining FK, not only column names.
    try:
        with engine.begin() as db:
            db.execute(text("UPDATE knowledge_node_sources SET material_id=999 WHERE id=71"))
    except IntegrityError as error:
        assert getattr(error.orig, "sqlstate", None) == "23503"
    else:
        raise AssertionError("Material source FK was lost")
    try:
        command.downgrade(config, OLD_HEAD)
    except RuntimeError as error:
        assert "Restore" in str(error)
    else:
        raise AssertionError("Lossy downgrade was silently accepted")
    verify(engine, path)
    command.check(config)
    print("FIELD_CLEANUP_EXERCISE_OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "verify", "seed", "exercise", "verify-restored"))
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    url = os.environ["DATABASE_URL"]
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("Online PostgreSQL is required")
    if args.action in {"seed", "exercise", "verify-restored"} and parsed.database != "field_cleanup_check":
        raise RuntimeError("Only the disposable field_cleanup_check database is allowed")
    engine = create_engine(url)
    config = Config("alembic.ini")
    try:
        if args.action == "prepare":
            write_manifest(engine, args.manifest)
        elif args.action == "seed":
            seed(engine, config, args.manifest)
        elif args.action == "exercise":
            exercise(engine, config, args.manifest)
        else:
            verify(engine, args.manifest, restored=args.action == "verify-restored")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()