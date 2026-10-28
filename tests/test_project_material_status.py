import pytest

from app.models.material import MaterialVersion, ParseStatus
from app.services import material_service


@pytest.fixture(autouse=True)
def isolated_material_storage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(material_service, "MATERIAL_STORAGE_DIR", tmp_path / "materials")


def _login(client, username: str) -> dict[str, str]:
    password = "material-status-test-password"
    assert client.post(
        "/users", json={"username": username, "password": password}
    ).status_code == 201
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _project(client, headers: dict[str, str], name: str) -> int:
    response = client.post("/projects", headers=headers, json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def _material(client, headers: dict[str, str], project_id: int) -> dict:
    response = client.post(
        "/materials",
        headers=headers,
        data={"name": "状态验证资料"},
        files={"file": ("status.md", b"# Status\n\nContent\n", "text/markdown")},
    )
    assert response.status_code == 201
    material = response.json()
    binding = client.post(
        f"/projects/{project_id}/materials/{material['material_id']}", headers=headers
    )
    assert binding.status_code == 201
    return material


def _list(client, headers: dict[str, str], project_id: int) -> list[dict]:
    response = client.get(f"/projects/{project_id}/materials", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_list_restores_version_and_reports_database_status(client, db_session) -> None:
    headers = _login(client, "status-owner")
    project_id = _project(client, headers, "状态恢复项目")
    material = _material(client, headers, project_id)
    version = db_session.get(MaterialVersion, material["version_id"])
    assert version is not None

    # 这里验证查询契约；真实入队/Worker 的状态迁移由已有回归测试保护。
    for state in ("UPLOADED", "QUEUED", "PARSING", "READY"):
        version.parse_status = state
        db_session.commit()
        items = _list(client, headers, project_id)
        assert len(items) == 1
        item = items[0]
        assert item["project_id"] == project_id
        assert item["material_id"] == material["material_id"]
        assert item["name"] == "状态验证资料"
        assert item["latest_version"] == {
            "version_id": version.id,
            "version_number": 1,
            "original_filename": "status.md",
            "parse_status": state,
            "parse_error_code": None,
            "parse_error_message": None,
        }
        assert "storage_object_key" not in item["latest_version"]
        single = client.get(
            f"/materials/{material['material_id']}/versions/{version.id}/parse",
            headers=headers,
        )
        assert single.status_code == 200
        assert single.json()["parse_status"] == state


def test_list_shows_latest_failed_version_instead_of_old_ready(client, db_session) -> None:
    headers = _login(client, "latest-status-owner")
    project_id = _project(client, headers, "最新版本项目")
    material = _material(client, headers, project_id)
    old = db_session.get(MaterialVersion, material["version_id"])
    assert old is not None
    old.parse_status = ParseStatus.READY.value
    latest = MaterialVersion(
        material_id=old.material_id,
        version_number=2,
        original_filename="new.md",
        normalized_format=old.normalized_format,
        mime_type=old.mime_type,
        size_bytes=old.size_bytes,
        content_hash=old.content_hash,
        storage_object_key="test-only/not-read.md",
        parse_status=ParseStatus.FAILED.value,
        parse_error_code="MATERIAL_CONTENT_EMPTY",
        parse_error_message="material contains no text",
    )
    db_session.add(latest)
    db_session.commit()

    items = _list(client, headers, project_id)
    assert len(items) == 1
    assert items[0]["latest_version"] == {
        "version_id": latest.id,
        "version_number": 2,
        "original_filename": "new.md",
        "parse_status": "FAILED",
        "parse_error_code": "MATERIAL_CONTENT_EMPTY",
        "parse_error_message": "material contains no text",
    }


def test_status_list_is_scoped_to_owner_project_and_active_bindings(client) -> None:
    owner = _login(client, "scoped-status-owner")
    other = _login(client, "scoped-status-other")
    first = _project(client, owner, "项目一")
    second = _project(client, owner, "项目二")
    material = _material(client, owner, first)

    assert _list(client, owner, second) == []
    path = f"/projects/{first}/materials"
    forbidden = client.get(path, headers=other)
    assert forbidden.status_code == 404
    assert forbidden.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert client.get(path).status_code == 401
    assert client.delete(
        f"{path}/{material['material_id']}", headers=owner
    ).status_code == 204
    assert _list(client, owner, first) == []