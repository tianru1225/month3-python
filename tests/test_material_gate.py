import json

import pytest
from fastapi import HTTPException

from app.models.learning_project import LearningProject
from app.models.material import Material, MaterialFormat, MaterialVersion
from app.models.material import ParseStatus
from app.models.project_material import ProjectMaterialBinding
from app.models.user import User
from app.services.material_gate import require_ready_materials_or_raise


def _create_user(db_session, username: str) -> User:
    user = User(username=username, password_hash="test-password-hash")
    db_session.add(user)
    db_session.flush()
    return user


def _create_project(db_session, user_id: int, name: str) -> LearningProject:
    project = LearningProject(
        user_id=user_id,
        name=name,
        goal="验证项目范围门禁",
        current_level="入门",
    )
    db_session.add(project)
    db_session.flush()
    return project


def _create_ready_version(
    db_session,
    user_id: int,
    *,
    parse_status: str = ParseStatus.READY.value,
) -> MaterialVersion:
    material = Material(user_id=user_id, name="门禁测试资料")
    db_session.add(material)
    db_session.flush()

    version = MaterialVersion(
        material_id=material.id,
        version_number=1,
        original_filename="guide.md",
        normalized_format=MaterialFormat.MARKDOWN.value,
        mime_type="text/markdown",
        size_bytes=20,
        content_hash=f"{material.id:064d}",
        storage_object_key=f"{user_id}/source.md",
        parse_status=parse_status,
    )
    db_session.add(version)
    db_session.flush()
    version.parsed_content_location = f"parsed/{material.id}/{version.id}.md"
    version.source_metadata = {
        "sources_path": f"parsed/{material.id}/{version.id}.sources.json"
    }
    return version


def _bind(db_session, project_id: int, material_id: int) -> None:
    db_session.add(
        ProjectMaterialBinding(
            project_id=project_id,
            material_id=material_id,
        )
    )


def _write_ready_output(storage_dir, version: MaterialVersion) -> None:
    parsed_path = storage_dir / version.parsed_content_location
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text("# Ready\n\ncontent\n", encoding="utf-8")
    parsed_path.with_suffix(".sources.json").write_text(
        json.dumps(
            {
                "material_version_id": version.id,
                "normalized_format": MaterialFormat.MARKDOWN.value,
                "blocks": [],
            }
        ),
        encoding="utf-8",
    )


def _assert_ready_required(db_session, project_id: int, user_id: int, tmp_path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_ready_materials_or_raise(
            db_session,
            project_id=project_id,
            user_id=user_id,
            storage_dir=tmp_path,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "MATERIAL_READY_REQUIRED"


def test_gate_returns_only_current_project_active_ready_material(
    db_session,
    tmp_path,
) -> None:
    user = _create_user(db_session, "gate-project-scope")
    first_project = _create_project(db_session, user.id, "第一个项目")
    second_project = _create_project(db_session, user.id, "第二个项目")
    first_version = _create_ready_version(db_session, user.id)
    second_version = _create_ready_version(db_session, user.id)
    _bind(db_session, first_project.id, first_version.material_id)
    _bind(db_session, second_project.id, second_version.material_id)
    db_session.commit()
    _write_ready_output(tmp_path, first_version)
    _write_ready_output(tmp_path, second_version)

    result = require_ready_materials_or_raise(
        db_session,
        project_id=first_project.id,
        user_id=user.id,
        storage_dir=tmp_path,
    )

    assert [version.id for version in result] == [first_version.id]


def test_unbound_ready_material_no_longer_passes_gate(db_session, tmp_path) -> None:
    user = _create_user(db_session, "gate-unbound")
    project = _create_project(db_session, user.id, "解绑门禁项目")
    version = _create_ready_version(db_session, user.id)
    binding = ProjectMaterialBinding(
        project_id=project.id,
        material_id=version.material_id,
    )
    db_session.add(binding)
    db_session.commit()
    _write_ready_output(tmp_path, version)

    binding.unbound_at = version.uploaded_at
    db_session.commit()
    _assert_ready_required(db_session, project.id, user.id, tmp_path)


@pytest.mark.parametrize(
    "parse_status",
    [
        ParseStatus.UPLOADED.value,
        ParseStatus.QUEUED.value,
        ParseStatus.PARSING.value,
        ParseStatus.FAILED.value,
    ],
)
def test_non_ready_status_is_rejected(
    db_session,
    tmp_path,
    parse_status: str,
) -> None:
    user = _create_user(db_session, f"gate-{parse_status.lower()}")
    project = _create_project(db_session, user.id, "状态门禁项目")
    version = _create_ready_version(
        db_session,
        user.id,
        parse_status=parse_status,
    )
    _bind(db_session, project.id, version.material_id)
    db_session.commit()
    _assert_ready_required(db_session, project.id, user.id, tmp_path)


@pytest.mark.parametrize(
    "output_kind",
    [
        "missing",
        "missing_source",
        "empty",
        "bad_source",
        "wrong_version",
        "wrong_format",
    ],
)
def test_invalid_ready_output_is_rejected(
    db_session,
    tmp_path,
    output_kind: str,
) -> None:
    user = _create_user(db_session, f"gate-output-{output_kind}")
    project = _create_project(db_session, user.id, "产物门禁项目")
    version = _create_ready_version(db_session, user.id)
    _bind(db_session, project.id, version.material_id)
    db_session.commit()

    parsed_path = tmp_path / version.parsed_content_location
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    if output_kind != "missing":
        parsed_path.write_text(
            "  \n" if output_kind == "empty" else "# Ready\n",
            encoding="utf-8",
        )

    source_map = {
        "material_version_id": version.id,
        "normalized_format": MaterialFormat.MARKDOWN.value,
        "blocks": [],
    }
    if output_kind == "wrong_version":
        source_map["material_version_id"] = version.id + 1
    if output_kind == "wrong_format":
        source_map["normalized_format"] = "txt"
    if output_kind not in {"missing", "missing_source", "bad_source"}:
        parsed_path.with_suffix(".sources.json").write_text(
            json.dumps(source_map),
            encoding="utf-8",
        )
    if output_kind == "bad_source":
        parsed_path.with_suffix(".sources.json").write_text(
            "{not-json}",
            encoding="utf-8",
        )

    _assert_ready_required(db_session, project.id, user.id, tmp_path)


def test_gate_enforces_project_and_material_owner(db_session, tmp_path) -> None:
    owner = _create_user(db_session, "gate-owner")
    other = _create_user(db_session, "gate-other")
    owner_project = _create_project(db_session, owner.id, "Owner 项目")
    other_project = _create_project(db_session, other.id, "Other 项目")
    owner_version = _create_ready_version(db_session, owner.id)
    other_version = _create_ready_version(db_session, other.id)
    _bind(db_session, owner_project.id, other_version.material_id)
    _bind(db_session, other_project.id, owner_version.material_id)
    db_session.commit()
    _write_ready_output(tmp_path, owner_version)
    _write_ready_output(tmp_path, other_version)

    _assert_ready_required(db_session, owner_project.id, owner.id, tmp_path)
    _assert_ready_required(db_session, other_project.id, other.id, tmp_path)


def test_multiple_ready_versions_are_sorted(db_session, tmp_path) -> None:
    user = _create_user(db_session, "gate-multiple")
    project = _create_project(db_session, user.id, "多资料项目")
    first = _create_ready_version(db_session, user.id)
    second = _create_ready_version(db_session, user.id)
    _bind(db_session, project.id, first.material_id)
    _bind(db_session, project.id, second.material_id)
    db_session.commit()
    _write_ready_output(tmp_path, first)
    _write_ready_output(tmp_path, second)

    result = require_ready_materials_or_raise(
        db_session,
        project_id=project.id,
        user_id=user.id,
        storage_dir=tmp_path,
    )

    assert [version.id for version in result] == sorted([first.id, second.id])
