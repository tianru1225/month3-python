#!/usr/bin/env bash
set -euo pipefail
umask 077

test -n "$SMOKE_USERNAME"
test -n "$PLAN_VERSION_ID"
test -n "$PASS_TASK_ID"
test -n "$REVISION_TASK_ID"

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
    user = db.scalar(select(User).where(User.username == os.environ["SMOKE_USERNAME"]))
    assert user is not None
    print(create_access_token(
        user.id, settings.jwt_secret_key.get_secret_value(),
        timedelta(minutes=5),
    ))
PY
)"

prepare_task() {
    local task_id="$1"
    docker compose exec -T \
      -e TASK_ID="$task_id" \
      -e PLAN_VERSION_ID="$PLAN_VERSION_ID" \
      -e SMOKE_USERNAME="$SMOKE_USERNAME" \
      api python - <<'PY'
import os
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.learning_task import LearningTask, TaskStatus
from app.models.user import User
from app.services.learning_task_service import transition_task_status

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username == os.environ["SMOKE_USERNAME"]))
    task = db.get(LearningTask, int(os.environ["TASK_ID"]))
    assert user is not None and task is not None
    assert task.plan_version_id == int(os.environ["PLAN_VERSION_ID"])
    if task.status == TaskStatus.DRAFT.value:
        transition_task_status(
            db, plan_version_id=task.plan_version_id, task_id=task.id,
            user_id=user.id, target_status=TaskStatus.READY,
        )
        db.refresh(task)
    if task.status == TaskStatus.READY.value:
        transition_task_status(
            db, plan_version_id=task.plan_version_id, task_id=task.id,
            user_id=user.id, target_status=TaskStatus.IN_PROGRESS,
        )
    else:
        assert task.status == TaskStatus.IN_PROGRESS.value, task.status
PY
}

request() {
    local expected="$1" method="$2" route="$3" output="$4"
    shift 4
    local code
    code="$(curl --silent --show-error --connect-timeout 5 --max-time 30 \
      --output "$output" --write-out '%{http_code}' \
      --request "$method" "$BASE_URL$route" "$@")"
    printf '%s %s -> %s\n' "$method" "$route" "$code"
    test "$code" = "$expected" || { cat "$output"; exit 1; }
}

prepare_task "$PASS_TASK_ID"
request 201 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$PASS_TASK_ID/evidence" \
  "$TMP/pass-evidence.json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"evidence_type":"TEXT_ANSWER","text_content":"已完成任务并验证关键结果。"}'

request 200 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$PASS_TASK_ID/evaluate" \
  "$TMP/pass-evaluation.json" \
  -H "Authorization: Bearer $TOKEN"

python - "$TMP/pass-evaluation.json" <<'PY'
import json
import sys
from pathlib import Path

body = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert body["evaluation"]["rule_status"] == "PASS"
assert body["evaluation"]["final_decision"] == "PASSED"
assert body["task_status"] == "PASSED"
print("text_answer_passed: passed")
PY

prepare_task "$REVISION_TASK_ID"
request 201 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$REVISION_TASK_ID/evidence" \
  "$TMP/revision-evidence.json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"evidence_type":"TEST_REPORT","test_report":{"command":"pytest -q","exit_code":1,"summary":"有失败检查","checks":[{"name":"tests","status":"FAILED","details":"1 failed"}]}}'

request 200 POST \
  "/plan-versions/$PLAN_VERSION_ID/tasks/$REVISION_TASK_ID/evaluate" \
  "$TMP/revision-evaluation.json" \
  -H "Authorization: Bearer $TOKEN"

python - "$TMP/revision-evaluation.json" <<'PY'
import json
import sys
from pathlib import Path

body = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert body["evaluation"]["rule_status"] == "FAIL"
assert body["evaluation"]["final_decision"] == "REVISION_REQUIRED"
assert body["task_status"] == "REVISION_REQUIRED"
print("test_report_revision_required: passed")
PY

echo "day144_evidence_smoke: passed"