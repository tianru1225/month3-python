import json

import pytest
from fastapi import HTTPException

from app.models.material import Material, MaterialFormat, MaterialVersion
from app.models.material import ParseStatus
from app.models.user import User
from app.services.material_gate import require_ready_materials_or_raise


def _create_user(db_session, username: str) -> User:
    user = User(username=username, password_hash="test-password-hash")
    db_session.add(user)
    db_session.flush()
    return user


def _create_material(db_session, user_id: int) -> Material:
    material = Material(user_id=user_id, name="门禁测试资料")
    db_session.add(material)
    db_session.flush()
    return material


def _create_version(
    db_session,
    material_id: int,
    *,
    parse_status: str = ParseStatus.READY.value,
) -> MaterialVersion:
    version = MaterialVersion(
        material_id=material_id,
        version_number=1,
        original_filename="guide.md",
        normalized_format=MaterialFormat.MARKDOWN.value,
        mime_type="text/markdown",
        size_bytes=20,
        content_hash="a" * 64,
        storage_object_key="1/guide.md",
        parse_status=parse_status,
    )
    db_session.add(version)
    db_session.flush()
    version.parsed_content_location = f"parsed/{material_id}/{version.id}.md"
    version.source_metadata = {
        "sources_path": f"parsed/{material_id}/{version.id}.sources.json"
    }
    return version


def _write_ready_output(storage_dir, version: MaterialVersion) -> None:
    parsed_path = storage_dir / version.parsed_content_location
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text("# Ready\n\ncontent\n", encoding="utf-8")
    parsed_path.with_suffix(".sources.json").write_text(
        json.dumps(
            {
                "material_version_id": version.id,
                "normalized_format": "markdown",
                "blocks": [],
            }
        ),
        encoding="utf-8",
    )


def _assert_ready_required(db_session, user_id: int, tmp_path) -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_ready_materials_or_raise(
            db_session,
            user_id=user_id,
            storage_dir=tmp_path,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "MATERIAL_READY_REQUIRED"


def test_ready_material_is_returned(db_session, tmp_path) -> None:
    user = _create_user(db_session, "gate-ready")
    material = _create_material(db_session, user.id)
    version = _create_version(db_session, material.id)
    db_session.commit()
    _write_ready_output(tmp_path, version)

    result = require_ready_materials_or_raise(
        db_session,
        user_id=user.id,
        storage_dir=tmp_path,
    )

    assert [item.id for item in result] == [version.id]


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
    material = _create_material(db_session, user.id)
    _create_version(
        db_session,
        material.id,
        parse_status=parse_status,
    )
    db_session.commit()

    _assert_ready_required(db_session, user.id, tmp_path)


@pytest.mark.parametrize("output_kind", ["missing", "empty", "bad_source"])
def test_invalid_ready_output_is_rejected(
    db_session,
    tmp_path,
    output_kind: str,
) -> None:
    user = _create_user(db_session, f"gate-output-{output_kind}")
    material = _create_material(db_session, user.id)
    version = _create_version(db_session, material.id)
    db_session.commit()

    parsed_path = tmp_path / version.parsed_content_location
    parsed_path.parent.mkdir(parents=True, exist_ok=True)

    if output_kind == "empty":
        parsed_path.write_text("  \n", encoding="utf-8")
        parsed_path.with_suffix(".sources.json").write_text(
            json.dumps(
                {
                    "material_version_id": version.id,
                    "normalized_format": "markdown",
                    "blocks": [],
                }
            ),
            encoding="utf-8",
        )
    elif output_kind == "bad_source":
        parsed_path.write_text("# Ready", encoding="utf-8")
        parsed_path.with_suffix(".sources.json").write_text(
            "{not-json}",
            encoding="utf-8",
        )

    _assert_ready_required(db_session, user.id, tmp_path)


def test_wrong_source_version_is_rejected(db_session, tmp_path) -> None:
    user = _create_user(db_session, "gate-wrong-source")
    material = _create_material(db_session, user.id)
    version = _create_version(db_session, material.id)
    db_session.commit()

    _write_ready_output(tmp_path, version)
    source_path = (tmp_path / version.parsed_content_location).with_suffix(
        ".sources.json"
    )
    source_map = json.loads(source_path.read_text(encoding="utf-8"))
    source_map["material_version_id"] = version.id + 1
    source_path.write_text(json.dumps(source_map), encoding="utf-8")

    _assert_ready_required(db_session, user.id, tmp_path)


def test_gate_does_not_use_another_users_ready_material(
    db_session,
    tmp_path,
) -> None:
    owner = _create_user(db_session, "gate-owner")
    other = _create_user(db_session, "gate-other")
    material = _create_material(db_session, owner.id)
    version = _create_version(db_session, material.id)
    db_session.commit()
    _write_ready_output(tmp_path, version)

    _assert_ready_required(db_session, other.id, tmp_path)


def test_multiple_ready_versions_are_sorted(db_session, tmp_path) -> None:
    user = _create_user(db_session, "gate-multiple")
    first_material = _create_material(db_session, user.id)
    second_material = _create_material(db_session, user.id)
    first = _create_version(db_session, first_material.id)
    second = _create_version(db_session, second_material.id)
    db_session.commit()
    _write_ready_output(tmp_path, first)
    _write_ready_output(tmp_path, second)

    result = require_ready_materials_or_raise(
        db_session,
        user_id=user.id,
        storage_dir=tmp_path,
    )

    assert [item.id for item in result] == sorted([first.id, second.id])
