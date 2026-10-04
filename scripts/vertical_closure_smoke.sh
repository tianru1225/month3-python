#!/usr/bin/env bash
set -euo pipefail
umask 077

test -n "$SMOKE_USERNAME"
test -n "$PROJECT_ID"
test -n "$MATERIAL_ID"
test -n "$MATERIAL_VERSION_ID"
test -n "$PLAN_VERSION_ID"
test -n "$PASS_TASK_ID"
test -n "$REVISION_TASK_ID"
test -n "$FINAL_TASK_ID"

BASE_URL="http://127.0.0.1:8080/api"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

TOKEN="$(docker compose exec -T -e SMOKE_USERNAME="$SMOKE_USERNAME" api python - <<'PY'
import os
from datetime import timedelta
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.user import User

with SessionLocal() as db:
    user = db.scalar(
        select(User).where(User.username == os.environ["SMOKE_USERNAME"])
    )
    assert user is not None
    print(
        create_access_token(
            user.id,
            settings.jwt_secret_key.get_secret_value(),
            timedelta(minutes=5),
        )
    )
PY
)"

request() {
  local expected="$1"
  local method="$2"
  local route="$3"
  local output="$4"
  shift 4
  local code
  code="$(curl --silent --show-error --connect-timeout 5 --max-time 30 \
    --output "$output" --write-out '%{http_code}' \
    --request "$method" "$BASE_URL$route" \
    -H "Authorization: Bearer $TOKEN" "$@")"
  printf '%s %s -> %s\n' "$method" "$route" "$code"
  if [[ "$code" != "$expected" ]]; then
    cat "$output"
    exit 1
  fi
}

json_assert() {
  local file="$1"
  shift
  python - "$file" "$@" <<'PY'
import json
import sys
from pathlib import Path

body = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
for expression in sys.argv[2:]:
    assert eval(expression, {"body": body}), expression
PY
}

echo "1/8 verify project ownership"
request 200 GET "/projects/$PROJECT_ID" "$TMP/project.json"
json_assert "$TMP/project.json" \
  'body["id"] == int(__import__("os").environ["PROJECT_ID"])'

echo "2/8 verify READY material through API"
request 200 GET \
  "/materials/$MATERIAL_ID/versions/$MATERIAL_VERSION_ID/parse" \
  "$TMP/material.json"
json_assert "$TMP/material.json" \
  'body["material_id"] == int(__import__("os").environ["MATERIAL_ID"])' \
  'body["version_id"] == int(__import__("os").environ["MATERIAL_VERSION_ID"])' \
  'body["parse_status"] == "READY"'

echo "3/8 verify published plan and initial task state"
docker compose exec -T \
  -e PLAN_VERSION_ID="$PLAN_VERSION_ID" \
  -e PASS_TASK_ID="$PASS_TASK_ID" \
  -e REVISION_TASK_ID="$REVISION_TASK_ID" \
  -e FINAL_TASK_ID="$FINAL_TASK_ID" \
  api python - <<'PY'
import os
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.learning_plan import PlanVersion, PlanVersionStatus
from app.models.learning_task import LearningTask, TaskStatus, TaskPrerequisite

with SessionLocal() as db:
    version = db.get(PlanVersion, int(os.environ["PLAN_VERSION_ID"]))
    assert version is not None
    assert version.status == PlanVersionStatus.PUBLISHED.value
    assert version.is_current is True

    expected = {
        int(os.environ["PASS_TASK_ID"]): TaskStatus.PASSED.value,
        int(os.environ["REVISION_TASK_ID"]): TaskStatus.REVISION_REQUIRED.value,
        int(os.environ["FINAL_TASK_ID"]): TaskStatus.DRAFT.value,
    }
    for task_id, expected_status in expected.items():
        task = db.get(LearningTask, task_id)
        assert task is not None
        assert task.plan_version_id == version.id
        assert task.status == expected_status

    edge = db.scalar(
        select(TaskPrerequisite).where(
            TaskPrerequisite.plan_version_id == version.id,
            TaskPrerequisite.task_id == int(os.environ["FINAL_TASK_ID"]),
            TaskPrerequisite.prerequisite_task_id
            == int(os.environ["REVISION_TASK_ID"]),
        )
    )
    assert edge is not None
print("initial_state: passed")
PY

echo "4/8 verify today's task API before retry"
request 200 GET \
  "/projects/$PROJECT_ID/plan-versions/$PLAN_VERSION_ID/today-tasks?target_date=2026-09-29" \
  "$TMP/today-before.json"
json_assert "$TMP/today-before.json" \
  'body["plan_version_id"] == int(__import__("os").environ["PLAN_VERSION_ID"])' \
  'any(task["id"] == int(__import__("os").environ["REVISION_TASK_ID"]) for task in body["tasks"])'

echo "5/8 move task 12 from REVISION_REQUIRED to IN_PROGRESS"
docker compose exec -T \
  -e PLAN_VERSION_ID="$PLAN_VERSION_ID" \
  -e REVISION_TASK_ID="$REVISION_TASK_ID" \
  -e SMOKE_USERNAME="$SMOKE_USERNAME" \
  api python - <<'PY'
import os
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.learning_task import TaskStatus
from app.models.user import User
from app.services.learning_task_service import transition_task_status

with SessionLocal() as db:
    user = db.scalar(
        select(User).where(User.username == os.environ["SMOKE_USERNAME"])
    )
    assert user is not None
    task = transition_task_status(
        db,
        plan_version_id=int(os.environ["PLAN_VERSION_ID"]),
        task_id=int(os.environ["REVISION_TASK_ID"]),
        user_id=user.id,
        target_status=TaskStatus.IN_PROGRESS,
    )
    assert task.status == TaskStatus.IN_PROGRESS.value
print("task_12_in_progress: passed")
PY

echo "6/8 submit and evaluate task 12"
request 201 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$REVISION_TASK_ID/evidence" \
  "$TMP/task12-evidence.json" \
  -H "Content-Type: application/json" \
  --data '{"evidence_type":"TEXT_ANSWER","text_content":"已按反馈修正，并重新验证关键结果。"}'
json_assert "$TMP/task12-evidence.json" \
  'body["source_kind"] == "USER"' \
  'body["attempt_number"] == 2'

request 200 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$REVISION_TASK_ID/evaluate" \
  "$TMP/task12-evaluation.json"
json_assert "$TMP/task12-evaluation.json" \
  'body["evaluation"]["rule_status"] == "PASS"' \
  'body["evaluation"]["final_decision"] == "PASSED"' \
  'body["task_status"] == "PASSED"'

echo "7/8 unlock and complete task 13"
docker compose exec -T \
  -e PLAN_VERSION_ID="$PLAN_VERSION_ID" \
  -e FINAL_TASK_ID="$FINAL_TASK_ID" \
  -e SMOKE_USERNAME="$SMOKE_USERNAME" \
  api python - <<'PY'
import os
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.learning_task import TaskStatus
from app.models.user import User
from app.services.learning_task_service import transition_task_status

with SessionLocal() as db:
    user = db.scalar(
        select(User).where(User.username == os.environ["SMOKE_USERNAME"])
    )
    assert user is not None
    task = transition_task_status(
        db,
        plan_version_id=int(os.environ["PLAN_VERSION_ID"]),
        task_id=int(os.environ["FINAL_TASK_ID"]),
        user_id=user.id,
        target_status=TaskStatus.READY,
    )
    assert task.status == TaskStatus.READY.value
    task = transition_task_status(
        db,
        plan_version_id=int(os.environ["PLAN_VERSION_ID"]),
        task_id=int(os.environ["FINAL_TASK_ID"]),
        user_id=user.id,
        target_status=TaskStatus.IN_PROGRESS,
    )
    assert task.status == TaskStatus.IN_PROGRESS.value
print("task_13_unlocked: passed")
PY

request 201 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$FINAL_TASK_ID/evidence" \
  "$TMP/task13-evidence.json" \
  -H "Content-Type: application/json" \
  --data '{"evidence_type":"TEST_REPORT","test_report":{"command":"pytest -q tests/test_evidence_acceptance.py","exit_code":0,"summary":"纵向闭环相关测试通过","checks":[{"name":"evidence_acceptance","status":"PASSED","details":"7 passed"}]}}'
request 200 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$FINAL_TASK_ID/evaluate" \
  "$TMP/task13-evaluation.json"
json_assert "$TMP/task13-evaluation.json" \
  'body["evaluation"]["rule_status"] == "PASS"' \
  'body["evaluation"]["final_decision"] == "PASSED"' \
  'body["task_status"] == "PASSED"'

echo "8/8 verify final task list and prerequisite completion"
request 200 GET \
  "/projects/$PROJECT_ID/plan-versions/$PLAN_VERSION_ID/today-tasks?target_date=2026-09-30" \
  "$TMP/today-after.json"
json_assert "$TMP/today-after.json" \
  'any(task["id"] == int(__import__("os").environ["FINAL_TASK_ID"]) and task["status"] == "PASSED" for task in body["tasks"])' \
  'all(task["prerequisites_complete"] for task in body["tasks"] if task["id"] == int(__import__("os").environ["FINAL_TASK_ID"]))'

docker compose exec -T \
  -e PASS_TASK_ID="$PASS_TASK_ID" \
  -e REVISION_TASK_ID="$REVISION_TASK_ID" \
  -e FINAL_TASK_ID="$FINAL_TASK_ID" \
  api python - <<'PY'
import os

from app.db.session import SessionLocal
from app.models.learning_task import LearningTask, TaskStatus

with SessionLocal() as db:
    for key in ("PASS_TASK_ID", "REVISION_TASK_ID", "FINAL_TASK_ID"):
        task = db.get(LearningTask, int(os.environ[key]))
        assert task is not None
        assert task.status == TaskStatus.PASSED.value
print("vertical_state: all three tasks PASSED")
PY

echo "vertical_closure_smoke: passed"