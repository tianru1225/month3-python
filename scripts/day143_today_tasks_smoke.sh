#!/usr/bin/env bash
set -euo pipefail
umask 077

test -n "$SMOKE_USERNAME"
test -n "$PROJECT_ID"
test -n "$PLAN_VERSION_ID"
test -n "$TARGET_DATE"

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
    assert user is not None, "smoke user not found"
    print(create_access_token(
        user.id, settings.jwt_secret_key.get_secret_value(),
        timedelta(minutes=5),
    ))
PY
)"

request() {
    local expected="$1" method="$2" route="$3" output="$4"
    shift 4
    local code
    code="$(curl --silent --show-error --connect-timeout 5 --max-time 30 \
        --output "$output" --write-out '%{http_code}' \
        --request "$method" "$BASE_URL$route" "$@")"
    printf '%s %s -> %s\n' "$method" "$route" "$code"
    if [ "$code" != "$expected" ]; then
        printf 'expected %s, got %s, body:\n' "$expected" "$code"
        cat "$output"
        printf '\n'
        return 1
    fi
}

ROUTE="/projects/$PROJECT_ID/plan-versions/$PLAN_VERSION_ID/today-tasks?target_date=$TARGET_DATE"
request 401 GET "$ROUTE" "$TMP/unauthorized.json"
request 200 GET "$ROUTE" "$TMP/today.json" \
    -H "Authorization: Bearer $TOKEN"

python - "$TMP/today.json" <<'PY'
import json
import os
import sys
from pathlib import Path

body = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert body["project_id"] == int(os.environ["PROJECT_ID"]), body
assert body["plan_version_id"] == int(os.environ["PLAN_VERSION_ID"]), body
assert body["target_date"] == os.environ["TARGET_DATE"], body
assert body["tasks"], "expected at least one task on target date"
positions = [task["position"] for task in body["tasks"]]
assert positions == sorted(positions), f"tasks not sorted: {positions}"
for task in body["tasks"]:
    assert task["scheduled_date"] == os.environ["TARGET_DATE"], task
    assert "prerequisites" in task, task
    assert "prerequisites_complete" in task, task
print(f"today_tasks: passed; count={len(body['tasks'])}")
PY

EMPTY_DATE="$(docker compose exec -T -e PLAN_VERSION_ID="$PLAN_VERSION_ID" api python - <<'PY'
import os
from datetime import timedelta

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.learning_task import LearningTask

with SessionLocal() as db:
    last = db.scalar(
        select(func.max(LearningTask.scheduled_date)).where(
            LearningTask.plan_version_id == int(os.environ["PLAN_VERSION_ID"])
        )
    )
    assert last is not None, "plan version has no tasks"
    print((last + timedelta(days=1)).isoformat())
PY
)"

request 200 GET \
    "/projects/$PROJECT_ID/plan-versions/$PLAN_VERSION_ID/today-tasks?target_date=$EMPTY_DATE" \
    "$TMP/empty.json" \
    -H "Authorization: Bearer $TOKEN"

python - "$TMP/empty.json" <<'PY'
import json
import sys
from pathlib import Path

body = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert body["tasks"] == [], f"expected no tasks, got {body['tasks']}"
print(f"boundary_date: passed; date={body['target_date']}")
PY

echo "day143_today_tasks_smoke: passed"