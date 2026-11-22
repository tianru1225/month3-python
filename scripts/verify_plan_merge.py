"""Read-only data checks; synthetic writes are restricted to plan_merge_check."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path

from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import make_url

OLD_HEAD = "c62f0a8e315d"
NEW_HEAD = "e73a1b9c406f"


def canonical(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def digest(rows):
    payload = json.dumps(rows, default=canonical, sort_keys=True, separators=(",", ":"))
    return {"rows": len(rows), "sha256": hashlib.sha256(payload.encode()).hexdigest()}


def migration():
    path = Path(__file__).resolve().parents[1] / "migrations/versions/e73a1b9c406f_merge_learning_plans.py"
    spec = importlib.util.spec_from_file_location("plan_merge_migration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(conn, before):
    metadata = MetaData()
    metadata.reflect(bind=conn)
    tables = {
        name: [dict(row) for row in conn.execute(select(table).order_by(table.c.id)).mappings()]
        for name, table in metadata.tables.items() if name != "alembic_version"
    }
    if before:
        plans = {row["id"]: row for row in tables["learning_plans"]}
        versions = tables.pop("plan_versions")
        merged = []
        for version in versions:
            header = plans[version["plan_id"]]
            merged.append({
                "id": version["id"], "project_id": header["project_id"],
                "content": version["content"],
                "provider_name": version["provider_name"], "model_name": version["model_name"],
                "created_at": version["created_at"],
                "updated_at": max(header["updated_at"], version["created_at"]),
                "locked_at": version["published_at"],
            })
        tables["learning_plans"] = sorted(merged, key=lambda row: row["id"])
        for name, old, new in (
            ("learning_tasks", "plan_version_id", "plan_id"),
            ("evidence", "plan_version_id", "plan_id"),
            ("task_prerequisites", "plan_version_id", "plan_id"),
            ("replan_proposals", "base_plan_version_id", "base_plan_id"),
        ):
            for row in tables[name]:
                row[new] = row.pop(old)
    return {name: digest(rows) for name, rows in sorted(tables.items())}


def seed(conn):
    # IDs deliberately differ between header and version.
    conn.execute(text("""
        INSERT INTO users (id, username, password_hash, status, created_at)
        VALUES (701,'plan-merge-fixture','not-a-login-password','ACTIVE',now())
    """))
    conn.execute(text("""
        INSERT INTO learning_projects (id,user_id,name,created_at,updated_at)
        VALUES (702,701,'Migration fixture',now(),now())
    """))
    conn.execute(text("""
        INSERT INTO learning_plans (id,project_id,name,created_at,updated_at)
        VALUES (703,702,'Legacy header',now(),now())
    """))
    conn.execute(text("""
        INSERT INTO plan_versions
          (id,plan_id,version_number,status,goal,content,source_kind,created_at,
           published_at,confirmed_by_user_id,is_current)
        VALUES (704,703,1,'PUBLISHED','Keep learning facts','{}','MANUAL',
                now(),now(),701,true)
    """))
    for task_id, position in ((705,1),(706,2)):
        conn.execute(text("""
            INSERT INTO learning_tasks
              (id,plan_version_id,position,scheduled_date,title,objective,instructions,
               steps,estimated_minutes,deliverable,acceptance_criteria,status,created_at,completed_at)
            VALUES (:id,704,:position,current_date,'Task','Objective','Instructions',
                    '["step"]',20,'Answer','["criterion"]','PASSED',now(),now())
        """), {"id": task_id, "position": position})
    conn.execute(text("""
        INSERT INTO task_prerequisites
            (id,plan_version_id,task_id,prerequisite_task_id,created_at)
        VALUES (707,704,706,705,now())
    """))
    conn.execute(text("""
        INSERT INTO evidence
            (id,plan_version_id,task_id,attempt_number,evidence_type,source_kind,
             text_content,submitted_by_user_id,submitted_at)
        VALUES (708,704,705,1,'TEXT_ANSWER','USER','preserve this answer',701,now())
    """))
    conn.execute(text("""
        INSERT INTO evaluations
          (id,evidence_id,rule_status,rule_result,human_decision,human_note,
           confirmed_by_user_id,confirmed_at,final_decision,finalized_by_user_id,
           finalized_at,created_at)
        VALUES (711,708,'PASS','{"checks":[]}','PASSED','historical result',701,now(),
                'PASSED',701,now(),now())
    """))
    conn.execute(text("""
        INSERT INTO replan_proposals
            (id,project_id,base_plan_version_id,created_by_user_id,trigger_code,reason,
             proposed_content,diff,status,created_at)
        VALUES (709,702,704,701,'USER_REQUEST','Historical suggestion','{}','{}','PENDING',now())
    """))
    conn.execute(text("""
        INSERT INTO audit_events
            (id,project_id,proposal_id,actor_user_id,event_type,payload,created_at)
        VALUES (710,702,709,701,'PROPOSAL_CREATED',json_build_object('base_plan_version_id', 704),now())
    """))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "prepare", "verify", "verify-before", "seed", "conflict", "constraints"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    url = make_url(os.environ["DATABASE_URL"])
    if url.get_backend_name() != "postgresql":
        raise SystemExit("PostgreSQL required")
    if args.action in ("seed", "conflict", "constraints") and url.database != "plan_merge_check":
        raise SystemExit("synthetic writes require the isolated plan_merge_check database")
    engine = create_engine(url)
    if args.action in ("seed", "conflict"):
        with engine.begin() as conn:
            if conn.scalar(text("SELECT version_num FROM alembic_version")) != OLD_HEAD:
                raise RuntimeError("fixture requires old schema")
            if args.action == "seed":
                if conn.scalar(text("SELECT count(*) FROM users")):
                    raise RuntimeError("seed requires an empty isolated database")
                seed(conn)
            else:
                conn.execute(text("""
                    INSERT INTO plan_versions
                      (id,plan_id,version_number,status,goal,content,source_kind,created_at,is_current)
                    VALUES (799,703,2,'DRAFT','Ambiguous','{}','MANUAL',now(),false)
                """))
        print("PLAN_MERGE_FIXTURE_OK")
        return
    if args.action == "constraints":
        from sqlalchemy.exc import IntegrityError
        with engine.connect() as conn:
            statements = [
                "INSERT INTO learning_plans (project_id,content,created_at,updated_at) "
                "VALUES (702,'{}',now(),now())",
                "UPDATE learning_plans SET provider_name='provider',model_name=NULL WHERE id=704",
                "UPDATE learning_plans SET provider_name=NULL,model_name='model' WHERE id=704",
                "UPDATE evidence SET plan_id=999999 WHERE id=708",
                "UPDATE task_prerequisites SET plan_id=999999 WHERE id=707",
                "UPDATE learning_tasks SET plan_id=999999 WHERE id=705",
                "UPDATE replan_proposals SET base_plan_id=999999 WHERE id=709",
            ]
            for sql in statements:
                try:
                    conn.execute(text(sql))
                except IntegrityError:
                    conn.rollback()
                else:
                    conn.rollback()
                    raise AssertionError("constraint unexpectedly accepted invalid data")
        print("PLAN_MERGE_CONSTRAINTS_OK")
        from datetime import date
        from sqlalchemy.orm import Session
        from app.services.evaluation_service import get_evaluation
        from app.services.learning_plan_service import get_plan
        from app.services.today_task_service import list_today_tasks_or_raise
        with Session(engine) as db:
            assert get_plan(db, plan_id=704, user_id=701).locked_at is not None
            result = list_today_tasks_or_raise(
                db, project_id=702, plan_id=704, user_id=701,
                target_date=db.scalar(text("SELECT current_date")) or date.today(),
            )
            assert [task.id for task in result.tasks] == [705, 706]
            assert result.tasks[1].prerequisites_complete
            assert get_evaluation(db, evaluation_id=711, user_id=701).final_decision == "PASSED"
        print("PLAN_MERGE_POSTGRES_SERVICES_OK")
        return
    with engine.connect() as conn:
        head = conn.scalar(text("SELECT version_num FROM alembic_version"))
        expected_head = NEW_HEAD if args.action == "verify" else OLD_HEAD
        if head != expected_head:
            raise RuntimeError(f"expected {expected_head}, got {head}")
        if args.action not in ("verify", "verify-before"):
            migration()._require_safe(conn)
        if args.action == "check":
            counts = {
                name: conn.scalar(text(f"SELECT count(*) FROM {name}"))
                for name in ("learning_plans", "plan_versions", "learning_tasks", "evidence")
            }
            print(json.dumps(counts))
            print("PLAN_MERGE_PREFLIGHT_OK")
            return
        if args.manifest is None:
            raise SystemExit("--manifest is required")
        current = snapshot(conn, before=False)
        if args.action == "prepare":
            # Never overwrite an earlier baseline.
            with args.manifest.open("x", encoding="utf-8") as output:
                json.dump({"before": current, "after": snapshot(conn, before=True)},
                          output, sort_keys=True, indent=2)
            print("PLAN_MERGE_PREPARED")
        else:
            if args.action == "verify" and "plan_versions" in inspect(conn).get_table_names():
                raise AssertionError("old version table still exists")
            if args.action == "verify":
                columns = {column["name"] for column in inspect(conn).get_columns("learning_plans")}
                expected_columns = {
                    "id", "project_id", "content", "provider_name", "model_name",
                    "created_at", "updated_at", "locked_at",
                }
                if columns != expected_columns:
                    raise AssertionError(f"unexpected learning_plans columns: {sorted(columns)}")
            saved = json.loads(args.manifest.read_text(encoding="utf-8"))
            expected = saved["after" if args.action == "verify" else "before"]
            if current != expected:
                changed = sorted(
                    name for name in current.keys() | expected.keys()
                    if current.get(name) != expected.get(name)
                )
                raise AssertionError(f"data mismatch: {changed}")
            print("PLAN_MERGE_DATA_OK" if args.action == "verify" else "PLAN_MERGE_RESTORE_OK")


if __name__ == "__main__":
    main()