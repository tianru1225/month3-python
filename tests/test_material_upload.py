from hashlib import sha256

import pytest
from sqlalchemy import func, select

from app.models.material import Material, MaterialVersion, ParseStatus
from app.services import material_service


@pytest.fixture(autouse=True)
def isolated_material_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        material_service, "MATERIAL_STORAGE_DIR", tmp_path / "materials"
    )


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "day127-secure-password"
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


def _upload(
    client,
    headers: dict[str, str],
    *,
    filename: str = "source.md",
    content_type: str = "text/markdown",
    content: bytes = b"# FastAPI",
):
    return client.post(
        "/materials",
        headers=headers,
        data={"name": "学习资料"},
        files={"file": (filename, content, content_type)},
    )


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("guide.md", "text/markdown"),
        ("readme.markdown", "text/plain"),
    ],
)
def test_upload_markdown_creates_owned_record_and_file(
    client,
    db_session,
    filename: str,
    content_type: str,
) -> None:
    headers = _register_and_login(client, f"upload-{filename.replace('.', '-')}")
    content = "# Guide\n\n正文".encode()

    response = _upload(
        client,
        headers,
        filename=filename,
        content_type=content_type,
        content=content,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["normalized_format"] == "markdown"
    assert body["parse_status"] == ParseStatus.UPLOADED.value
    assert body["content_hash"] == sha256(content).hexdigest()

    version = db_session.get(MaterialVersion, body["version_id"])
    material = db_session.get(Material, body["material_id"])
    assert material is not None
    assert version is not None
    assert version.material_id == material.id
    assert (
        material_service.MATERIAL_STORAGE_DIR.joinpath(
            version.storage_object_key
        ).read_bytes()
        == content
    )


@pytest.mark.parametrize("filename", ["notes.txt", "book.pdf", "tool.exe"])
def test_upload_rejects_non_markdown_filename(
    client, db_session, filename: str
) -> None:
    headers = _register_and_login(client, f"reject-{filename.replace('.', '-')}")
    response = _upload(client, headers, filename=filename)

    assert response.status_code in {400, 415}
    assert response.json()["detail"]["code"] in {
        "MATERIAL_FILENAME_INVALID",
        "MATERIAL_FORMAT_UNSUPPORTED",
    }
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0


def test_upload_rejects_mime_mismatch(client, db_session) -> None:
    headers = _register_and_login(client, "upload-mime-mismatch")
    response = _upload(
        client,
        headers,
        filename="guide.md",
        content_type="application/pdf",
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "MATERIAL_MIME_INVALID"
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0


def test_upload_requires_bearer_token(client) -> None:
    response = _upload(client, {})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


def test_upload_rejects_empty_file(client, db_session) -> None:
    headers = _register_and_login(client, "upload-empty")
    response = _upload(client, headers, content=b"")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MATERIAL_FILE_EMPTY"
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0


def test_upload_rejects_file_over_limit(client, db_session, monkeypatch) -> None:
    monkeypatch.setattr(material_service, "MATERIAL_MAX_UPLOAD_BYTES", 4)
    headers = _register_and_login(client, "upload-too-large")
    response = _upload(client, headers, content=b"12345")

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "MATERIAL_FILE_TOO_LARGE"
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0
