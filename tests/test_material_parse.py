import json

import pytest
from sqlalchemy.orm import Session

from app.models.material import MaterialVersion, ParseStatus
from app.parsers.markdown_parser import parse_markdown
from app.repositories.material_repository import mark_version_queued
from app.services import material_service
from app.services.material_service import process_material_version


@pytest.fixture(autouse=True)
def isolated_material_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        material_service,
        "MATERIAL_STORAGE_DIR",
        tmp_path / "materials",
    )


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "day130-parse-password"
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


def _upload(client, headers, content: bytes = b"# Root\n\nbody\n") -> dict:
    response = client.post(
        "/materials",
        headers=headers,
        data={"name": "解析测试资料"},
        files={"file": ("guide.md", content, "text/markdown")},
    )
    assert response.status_code == 201
    return response.json()


def _queued_version(db_session: Session, body: dict) -> MaterialVersion:
    version = db_session.get(MaterialVersion, body["version_id"])
    assert version is not None
    mark_version_queued(db_session, version, job_id="test-job-id")
    return version


def test_parser_emits_structured_list_and_table_blocks() -> None:
    document = parse_markdown(
        b"# Root\n\n- one\n- two\n\n| name | value |\n| --- | --- |\n| a | b |\n"
    )
    assert [block["type"] for block in document.blocks] == [
        "heading",
        "list",
        "table",
    ]
    assert document.blocks[1]["source"]["section_path"] == ["Root"]


def test_parser_keeps_code_block_and_ignores_inner_heading() -> None:
    document = parse_markdown(
        b"# Root\n\n```python\n# not a heading\nprint('ok')\n```\n"
    )
    assert [block["type"] for block in document.blocks] == [
        "heading",
        "code_block",
    ]
    assert len(document.headings) == 1


def test_worker_processing_writes_ready_result(client, db_session) -> None:
    headers = _register_and_login(client, "worker-ready")
    content = b"# Root\n\n## Child\n\nbody\n"
    body = _upload(client, headers, content)
    version = _queued_version(db_session, body)

    process_material_version(db_session, version)

    assert version.parse_status == ParseStatus.READY.value
    assert version.parse_job_id == "test-job-id"
    assert version.parser_name == "markdown-token-parser"
    parsed_path = (
        material_service.MATERIAL_STORAGE_DIR / version.parsed_content_location
    )
    assert parsed_path.read_bytes() == content
    source_map = json.loads(
        parsed_path.with_suffix(".sources.json").read_text(encoding="utf-8")
    )
    assert source_map["material_version_id"] == version.id


@pytest.mark.parametrize(
    ("content", "error_code"),
    [
        (b"", "MATERIAL_CONTENT_EMPTY"),
        (b"\xff\xfe", "MATERIAL_SOURCE_INVALID_UTF8"),
    ],
)
def test_worker_processing_persists_content_failure(
    client,
    db_session,
    content: bytes,
    error_code: str,
) -> None:
    headers = _register_and_login(client, f"worker-{error_code.lower()}")
    body = _upload(client, headers, b"# placeholder")
    version = _queued_version(db_session, body)
    source_path = material_service.MATERIAL_STORAGE_DIR / version.storage_object_key
    source_path.write_bytes(content)

    process_material_version(db_session, version)

    assert version.parse_status == ParseStatus.FAILED.value
    assert version.parse_error_code == error_code
    assert version.processed_at is not None


def test_worker_processing_persists_missing_source(client, db_session) -> None:
    headers = _register_and_login(client, "worker-missing-source")
    body = _upload(client, headers)
    version = _queued_version(db_session, body)
    source_path = material_service.MATERIAL_STORAGE_DIR / version.storage_object_key
    source_path.unlink()

    process_material_version(db_session, version)

    assert version.parse_status == ParseStatus.FAILED.value
    assert version.parse_error_code == "MATERIAL_SOURCE_NOT_FOUND"


def test_worker_unexpected_error_is_persisted_and_raised(
    client,
    db_session,
    monkeypatch,
) -> None:
    headers = _register_and_login(client, "worker-unexpected-error")
    body = _upload(client, headers)
    version = _queued_version(db_session, body)

    def fail_parser(content: bytes):
        raise RuntimeError("unexpected parser failure")

    monkeypatch.setattr(material_service, "parse_markdown", fail_parser)

    with pytest.raises(RuntimeError, match="material parse worker failed"):
        process_material_version(db_session, version)

    assert version.parse_status == ParseStatus.FAILED.value
    assert version.parse_error_code == "MATERIAL_PARSE_ERROR"
