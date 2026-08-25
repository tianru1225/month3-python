from hashlib import sha256

import pytest
from sqlalchemy import func, select

from app.models.material import Material, MaterialVersion, ParseStatus
from app.services import material_service


@pytest.fixture(autouse=True)
def isolated_material_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        material_service,
        "MATERIAL_STORAGE_DIR",
        tmp_path / "materials",
    )


def _register_and_login(client, username: str) -> dict[str, str]:
    password = "day126-secure-password"
    register = client.post(
        "/users",
        json={"username": username, "password": password},
    )
    assert register.status_code == 201

    login = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _upload(
    client,
    headers: dict[str, str],
    *,
    name: str = "学习资料",
    description: str | None = None,
    filename: str = "source.md",
    content_type: str = "text/markdown",
    content: bytes = b"# FastAPI",
):
    data = {"name": name}
    if description is not None:
        data["description"] = description
    return client.post(
        "/materials",
        headers=headers,
        data=data,
        files={"file": (filename, content, content_type)},
    )


@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_format"),
    [
        ("guide.md", "text/markdown", b"# Guide", "markdown"),
        ("notes.txt", "text/plain", b"plain notes", "txt"),
        ("book.pdf", "application/pdf", b"%PDF-1.4\nexample", "text_pdf"),
    ],
)
def test_upload_supported_material_creates_owned_records_and_file(
    client,
    db_session,
    filename: str,
    content_type: str,
    content: bytes,
    expected_format: str,
) -> None:
    headers = _register_and_login(client, f"upload-{expected_format}")

    response = _upload(
        client,
        headers,
        name="  FastAPI 学习资料  ",
        description="  第一版资料  ",
        filename=filename,
        content_type=content_type,
        content=content,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "FastAPI 学习资料"
    assert body["description"] == "第一版资料"
    assert body["enabled"] is True
    assert body["version_number"] == 1
    assert body["original_filename"] == filename
    assert body["normalized_format"] == expected_format
    assert body["mime_type"] == content_type
    assert body["size_bytes"] == len(content)
    assert body["content_hash"] == sha256(content).hexdigest()
    assert body["parse_status"] == ParseStatus.UPLOADED.value
    assert "user_id" not in body
    assert "storage_object_key" not in body

    material = db_session.get(Material, body["material_id"])
    version = db_session.get(MaterialVersion, body["version_id"])
    assert material is not None
    assert version is not None
    assert material.user_id is not None
    assert version.material_id == material.id
    assert version.version_number == 1
    assert version.parse_status == ParseStatus.UPLOADED.value

    stored_path = material_service.MATERIAL_STORAGE_DIR / version.storage_object_key
    assert stored_path.is_file()
    assert stored_path.read_bytes() == content
    assert filename not in version.storage_object_key


def test_markdown_extension_accepts_text_plain(client) -> None:
    headers = _register_and_login(client, "upload-markdown-plain")

    response = _upload(
        client,
        headers,
        filename="readme.markdown",
        content_type="text/plain",
    )

    assert response.status_code == 201
    assert response.json()["normalized_format"] == "markdown"
    assert response.json()["mime_type"] == "text/plain"


def test_upload_requires_bearer_token(client) -> None:
    response = _upload(client, {})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTH_REQUIRED"


@pytest.mark.parametrize("filename", ["../escape.md", r"..\escape.md", "tool.exe"])
def test_upload_rejects_dangerous_or_unsupported_filename(
    client,
    db_session,
    filename: str,
) -> None:
    headers = _register_and_login(
        client,
        f"upload-bad-name-{abs(hash(filename))}",
    )

    response = _upload(client, headers, filename=filename)

    assert response.status_code in {400, 415}
    assert response.json()["detail"]["code"] in {
        "MATERIAL_FILENAME_INVALID",
        "MATERIAL_FORMAT_UNSUPPORTED",
    }
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0
    assert not any(
        path.is_file() for path in material_service.MATERIAL_STORAGE_DIR.rglob("*")
    )


def test_upload_rejects_mime_mismatch(client, db_session) -> None:
    headers = _register_and_login(client, "upload-mime-mismatch")

    response = _upload(
        client,
        headers,
        filename="fake.pdf",
        content_type="text/plain",
        content=b"not a pdf",
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "MATERIAL_MIME_INVALID"
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0


def test_upload_rejects_empty_file(client, db_session) -> None:
    headers = _register_and_login(client, "upload-empty")

    response = _upload(client, headers, content=b"")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MATERIAL_FILE_EMPTY"
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0


def test_upload_rejects_file_over_limit(
    client,
    db_session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(material_service, "MATERIAL_MAX_UPLOAD_BYTES", 4)
    headers = _register_and_login(client, "upload-too-large")

    response = _upload(client, headers, content=b"12345")

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "MATERIAL_FILE_TOO_LARGE"
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0
    assert not any(
        path.is_file() for path in material_service.MATERIAL_STORAGE_DIR.rglob("*")
    )


def test_upload_rejects_blank_material_name(client, db_session) -> None:
    headers = _register_and_login(client, "upload-blank-name")

    response = _upload(client, headers, name="   ")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MATERIAL_NAME_INVALID"
    assert db_session.scalar(select(func.count()).select_from(Material)) == 0
