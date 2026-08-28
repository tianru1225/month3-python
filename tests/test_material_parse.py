import json

import pytest
from sqlalchemy.orm import Session

from app.models.material import MaterialVersion, ParseStatus
from app.parsers.markdown_parser import parse_markdown
from app.services import material_service


@pytest.fixture(autouse=True)
def isolated_material_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        material_service, "MATERIAL_STORAGE_DIR", tmp_path / "materials"
    )


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "day127-parse-password"
    assert (
        client.post(
            "/users",
            json={"username": username, "password": password},
        ).status_code
        == 201
    )
    response = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _upload(client, headers, content: bytes = b"# Root\n\n## Child\n\nbody\n"):
    return client.post(
        "/materials",
        headers=headers,
        data={"name": "解析测试资料"},
        files={"file": ("guide.md", content, "text/markdown")},
    )


def _parse(client, headers, body):
    return client.post(
        f"/materials/{body['material_id']}/versions/{body['version_id']}/parse",
        headers=headers,
    )


def test_parser_emits_structured_list_and_table_blocks() -> None:
    content = b"# Root\n\n- one\n- two\n\n| name | value |\n| --- | --- |\n| a | b |\n"
    document = parse_markdown(content)
    assert [block["type"] for block in document.blocks] == [
        "heading",
        "list",
        "table",
    ]
    assert document.blocks[1]["source"]["section_path"] == ["Root"]
    assert document.blocks[2]["source"]["section_path"] == ["Root"]


def test_parser_keeps_code_block_and_ignores_heading_marker_inside() -> None:
    content = b"# Root\n\n```python\n# not a heading\nprint('ok')\n```\n"

    document = parse_markdown(content)

    assert [block["type"] for block in document.blocks] == [
        "heading",
        "code_block",
    ]
    assert document.headings == [
        {"line": 1, "level": 1, "text": "Root", "section_path": ["Root"]}
    ]
    assert document.blocks[1]["language"] == "python"
    assert document.blocks[1]["source"]["section_path"] == ["Root"]


def test_parse_markdown_writes_ready_result_and_source_map(client) -> None:
    headers = _register_and_login(client, "parse-ready")
    content = b"# Root\n\n## Child\n\nbody\n"
    upload = _upload(client, headers, content)
    assert upload.status_code == 201

    response = _parse(client, headers, upload.json())

    assert response.status_code == 200
    body = response.json()
    assert body["parse_status"] == ParseStatus.READY.value
    assert body["normalized_format"] == "markdown"
    assert body["parser_name"] == "markdown-token-parser"
    assert body["parser_version"] == "markdown-it-py-3.0.0"
    assert body["content_summary"] == "# Root ## Child body"
    assert body["source_metadata"]["headings"] == [
        {"line": 1, "level": 1, "text": "Root", "section_path": ["Root"]},
        {
            "line": 3,
            "level": 2,
            "text": "Child",
            "section_path": ["Root", "Child"],
        },
    ]

    parsed_path = (
        material_service.MATERIAL_STORAGE_DIR / body["parsed_content_location"]
    )
    source_path = parsed_path.with_suffix(".sources.json")
    assert parsed_path.read_bytes() == content
    source_map = json.loads(source_path.read_text(encoding="utf-8"))
    for block in source_map["blocks"]:
        assert (
            content.decode("utf-8")[block["char_start"] : block["char_end"]]
            == block["text"]
        )


@pytest.mark.parametrize(
    ("content", "error_code"),
    [
        (b"", "MATERIAL_CONTENT_EMPTY"),
        (b"\xff\xfe", "MATERIAL_SOURCE_INVALID_UTF8"),
    ],
)
def test_parse_failures_are_persisted(
    client,
    db_session: Session,
    content: bytes,
    error_code: str,
) -> None:
    headers = _register_and_login(client, f"parse-failure-{error_code}")
    upload = _upload(client, headers, b"# placeholder")
    body = upload.json()
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    (material_service.MATERIAL_STORAGE_DIR / version.storage_object_key).write_bytes(
        content
    )

    response = _parse(client, headers, body)

    assert response.status_code == 200
    assert response.json()["parse_status"] == ParseStatus.FAILED.value
    assert response.json()["parse_error_code"] == error_code
    assert response.json()["processed_at"] is not None


def test_parse_requires_owner(client) -> None:
    owner_headers = _register_and_login(client, "parse-owner")
    other_headers = _register_and_login(client, "parse-other")
    upload = _upload(client, owner_headers)

    response = _parse(client, other_headers, upload.json())

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MATERIAL_VERSION_NOT_FOUND"


def test_parse_missing_source_is_persisted(client, db_session: Session) -> None:
    headers = _register_and_login(client, "parse-missing-source")
    upload = _upload(client, headers)
    body = upload.json()
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    (material_service.MATERIAL_STORAGE_DIR / version.storage_object_key).unlink()

    response = _parse(client, headers, body)

    assert response.status_code == 200
    assert response.json()["parse_status"] == ParseStatus.FAILED.value
    assert response.json()["parse_error_code"] == "MATERIAL_SOURCE_NOT_FOUND"


def test_failed_parse_can_retry_after_source_is_fixed(
    client,
    db_session: Session,
) -> None:
    headers = _register_and_login(client, "parse-retry")
    upload = _upload(client, headers)
    body = upload.json()
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    source_path = material_service.MATERIAL_STORAGE_DIR / version.storage_object_key
    source_path.write_bytes(b"")

    failed = _parse(client, headers, body)
    assert failed.json()["parse_status"] == ParseStatus.FAILED.value

    source_path.write_bytes(b"# fixed")
    ready = _parse(client, headers, body)
    assert ready.status_code == 200
    assert ready.json()["parse_status"] == ParseStatus.READY.value


def test_ready_parse_is_idempotent(client) -> None:
    headers = _register_and_login(client, "parse-idempotent")
    upload = _upload(client, headers)
    body = upload.json()

    first = _parse(client, headers, body)
    first_body = first.json()
    parsed_path = (
        material_service.MATERIAL_STORAGE_DIR / first_body["parsed_content_location"]
    )
    first_content = parsed_path.read_bytes()

    second = _parse(client, headers, body)

    assert second.status_code == 200
    assert second.json() == first_body
    assert parsed_path.read_bytes() == first_content


def test_parse_requires_bearer_token(client) -> None:
    upload_headers = _register_and_login(client, "parse-auth")
    upload = _upload(client, upload_headers)

    response = _parse(client, {}, upload.json())

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"
