#!/usr/bin/env bash
set -euo pipefail
umask 077

# Run from ~/month3-python with its virtual environment activated.
SOURCE_FILE="${1:?Usage: bash scripts/day141_material_smoke.sh /path/to/notes.md}"
BASE_URL="http://127.0.0.1:8080/api"
RUN_ID="day141-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
OUT="artifacts/$RUN_ID"
mkdir -p "$OUT"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT

python - "$SOURCE_FILE" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
content = path.read_bytes()
assert path.suffix.lower() in {".md", ".markdown"}
assert 0 < len(content) <= 10 * 1024 * 1024
assert content.decode("utf-8").strip()
print(f"source_precheck: passed; bytes={len(content)}")
PY

json_field() {
    python - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(value[sys.argv[2]])
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
    if [[ "$code" != "$expected" ]]; then
        echo "Expected HTTP $expected; stopped. Check API/worker logs locally." >&2
        return 1
    fi
}

USERNAME="$RUN_ID"
echo "New acceptance account: $USERNAME"
read -r -s -p "Set a password (8-128 characters; remember it for Day142): " PASSWORD
echo
export USERNAME PASSWORD
python - "$TMP/login.json" <<'PY'
import json
import os
import sys
from pathlib import Path

password = os.environ["PASSWORD"]
assert 8 <= len(password) <= 128
Path(sys.argv[1]).write_text(
    json.dumps({"username": os.environ["USERNAME"], "password": password}),
    encoding="utf-8",
)
PY
unset PASSWORD
request 201 POST /users "$TMP/user.json" \
    -H 'Content-Type: application/json' --data-binary "@$TMP/login.json"
USER_ID="$(json_field "$TMP/user.json" id)"
request 200 POST /auth/login "$TMP/token.json" \
    -H 'Content-Type: application/json' --data-binary "@$TMP/login.json"
printf 'Authorization: Bearer %s\n' \
    "$(json_field "$TMP/token.json" access_token)" > "$TMP/auth.header"
rm -f -- "$TMP/token.json" "$TMP/login.json"

request 201 POST /projects "$TMP/project.json" \
    -H "@$TMP/auth.header" -H 'Content-Type: application/json' \
    --data-binary '{"name":"Python basics from real notes","goal":"Learn Python syntax, functions and collections using the uploaded notes","current_level":"beginner","daily_minutes":60,"weekly_days":5,"expected_outcome":"Explain the examples and complete small exercises"}'
PROJECT_ID="$(json_field "$TMP/project.json" id)"
request 201 POST /materials "$TMP/upload.json" \
    -H "@$TMP/auth.header" --form-string 'name=Python learning notes' \
    -F "file=@$SOURCE_FILE;filename=python-notes.md;type=text/markdown"
MATERIAL_ID="$(json_field "$TMP/upload.json" material_id)"
VERSION_ID="$(json_field "$TMP/upload.json" version_id)"
CONTENT_HASH="$(json_field "$TMP/upload.json" content_hash)"
export USER_ID PROJECT_ID MATERIAL_ID VERSION_ID CONTENT_HASH

python - "$SOURCE_FILE" "$TMP/upload.json" "$OUT/summary.json" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

content = Path(sys.argv[1]).read_bytes()
upload = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert upload["parse_status"] == "UPLOADED"
assert upload["size_bytes"] == len(content)
assert upload["content_hash"] == hashlib.sha256(content).hexdigest()
summary = {key.lower(): int(os.environ[key]) for key in (
    "USER_ID", "PROJECT_ID", "MATERIAL_ID", "VERSION_ID"
)}
summary.update(
    username=os.environ["USERNAME"],
    content_hash=upload["content_hash"],
    size_bytes=len(content),
    result="incomplete",
)
Path(sys.argv[3]).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY
echo "Run summary: $OUT/summary.json"

BIND_ROUTE="/projects/$PROJECT_ID/materials/$MATERIAL_ID"
PARSE_ROUTE="/materials/$MATERIAL_ID/versions/$VERSION_ID/parse"
request 201 POST "$BIND_ROUTE" "$TMP/binding.json" -H "@$TMP/auth.header"
request 200 POST "$BIND_ROUTE" "$TMP/binding-again.json" -H "@$TMP/auth.header"
test "$(json_field "$TMP/binding.json" id)" = "$(json_field "$TMP/binding-again.json" id)"
request 200 GET "/projects/$PROJECT_ID/materials" "$TMP/bindings.json" -H "@$TMP/auth.header"
python - "$TMP/bindings.json" <<'PY'
import json
import os
import sys
from pathlib import Path

bindings = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert len(bindings) == 1
assert bindings[0]["material_id"] == int(os.environ["MATERIAL_ID"])
assert bindings[0]["project_id"] == int(os.environ["PROJECT_ID"])
assert bindings[0]["unbound_at"] is None
PY

# This gate has no HTTP route; call the existing service in the API container.
check_gate() {
    docker compose exec -T \
        -e USER_ID="$USER_ID" -e PROJECT_ID="$PROJECT_ID" \
        -e VERSION_ID="$VERSION_ID" -e CONTENT_HASH="$CONTENT_HASH" \
        -e EXPECT_READY="$1" api python - <<'PY'
import hashlib
import json
import os

from fastapi import HTTPException

from app.db.session import SessionLocal
from app.services.material_gate import require_ready_materials_or_raise
from app.services.material_service import MATERIAL_STORAGE_DIR

ready = os.environ["EXPECT_READY"] == "yes"
with SessionLocal() as db:
    try:
        versions = require_ready_materials_or_raise(
            db,
            project_id=int(os.environ["PROJECT_ID"]),
            user_id=int(os.environ["USER_ID"]),
            storage_dir=MATERIAL_STORAGE_DIR,
        )
    except HTTPException as exc:
        assert not ready, "READY material unexpectedly rejected"
        assert exc.status_code == 409
        assert exc.detail["code"] == "MATERIAL_READY_REQUIRED"
        print("gate_before_parse: rejected as expected")
    else:
        assert ready, "UPLOADED material must not be usable"
        assert [v.id for v in versions] == [int(os.environ["VERSION_ID"])]
        version = versions[0]
        original = (MATERIAL_STORAGE_DIR / version.storage_object_key).read_bytes()
        assert hashlib.sha256(original).hexdigest() == os.environ["CONTENT_HASH"]
        assert version.content_hash == os.environ["CONTENT_HASH"]
        parsed_path = MATERIAL_STORAGE_DIR / version.parsed_content_location
        text = parsed_path.read_bytes().decode("utf-8")
        assert text == original.decode("utf-8")
        sources = json.loads(parsed_path.with_suffix(".sources.json").read_text(encoding="utf-8"))
        assert sources["material_version_id"] == version.id
        assert sources["normalized_format"] == "markdown"
        blocks = sources["blocks"]
        assert blocks, "real notes should contain source blocks"
        lines = text.splitlines()
        for block in blocks:
            start, end = block["char_start"], block["char_end"]
            assert 0 <= start < end <= len(text)
            assert text[start:end] == block["text"]
            assert 1 <= block["line_start"] <= block["line_end"] <= len(lines)
            assert block["source"]["line_start"] == block["line_start"]
            assert block["source"]["line_end"] == block["line_end"]
        assert version.source_metadata["line_count"] == len(lines)
        assert version.source_metadata["headings"]
        print(f"gate_after_parse: passed; lines={len(lines)}; blocks={len(blocks)}")
PY
}

check_gate no
request 401 GET "/projects/$PROJECT_ID" "$TMP/anonymous.json"

request 202 POST "$PARSE_ROUTE" "$TMP/queued.json" -H "@$TMP/auth.header"
JOB_ID="$(json_field "$TMP/queued.json" job_id)"
test -n "$JOB_ID"
test "$JOB_ID" != "None"
STATUS=""
for ((attempt = 1; attempt <= 60; attempt++)); do
    request 200 GET "$PARSE_ROUTE" "$TMP/status.json" -H "@$TMP/auth.header"
    STATUS="$(json_field "$TMP/status.json" parse_status)"
    echo "parse_status=$STATUS"
    case "$STATUS" in
        READY) break ;;
        FAILED)
            echo "parse_error_code=$(json_field "$TMP/status.json" parse_error_code)" >&2
            exit 1 ;;
        QUEUED|PARSING) sleep 2 ;;
        *) echo "Unexpected parse status: $STATUS" >&2; exit 1 ;;
    esac
done
test "$STATUS" = "READY" || { echo "Timed out waiting for READY" >&2; exit 1; }
test "$(json_field "$TMP/status.json" parse_job_id)" = "$JOB_ID"
request 200 POST "$PARSE_ROUTE" "$TMP/duplicate.json" -H "@$TMP/auth.header"
test "$(json_field "$TMP/duplicate.json" job_id)" = "$JOB_ID"
test "$(json_field "$TMP/duplicate.json" parse_status)" = "READY"
check_gate yes

python - "$OUT/summary.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
summary = json.loads(path.read_text(encoding="utf-8"))
summary["result"] = "passed"
summary["parse_status"] = "READY"
path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
PY
echo "day141_material_project_smoke: passed"
echo "Keep this account, project and material for Day142. No database cleanup was performed."
