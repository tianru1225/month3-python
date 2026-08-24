import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.material import (
    Material,
    MaterialFormat,
    MaterialVersion,
    ParseStatus,
    utc_now,
)
from app.models.user import User


def _create_user(db_session, username: str = "material-owner") -> User:
    user = User(username=username, password_hash="test-password-hash")
    db_session.add(user)
    db_session.flush()
    return user


def _create_material(db_session, user_id: int, name: str = "Python 资料") -> Material:
    material = Material(user_id=user_id, name=name)
    db_session.add(material)
    db_session.flush()
    return material


def _create_version(
    db_session,
    material_id: int,
    *,
    version_number: int = 1,
    normalized_format: str = MaterialFormat.MARKDOWN.value,
    parse_status: str = ParseStatus.UPLOADED.value,
) -> MaterialVersion:
    version = MaterialVersion(
        material_id=material_id,
        version_number=version_number,
        original_filename="python.md",
        normalized_format=normalized_format,
        mime_type="text/markdown",
        size_bytes=128,
        content_hash="a" * 64,
        storage_object_key="materials/1/versions/1/python.md",
        parse_status=parse_status,
    )
    db_session.add(version)
    return version


def test_material_and_version_persist_with_defaults(db_session) -> None:
    user = _create_user(db_session)
    material = _create_material(db_session, user.id)
    version = _create_version(db_session, material.id)
    version.source_metadata = {"line_start": 1, "line_end": 10}
    db_session.commit()

    saved_material = db_session.scalar(
        select(Material).where(Material.id == material.id)
    )
    saved_version = db_session.scalar(
        select(MaterialVersion).where(MaterialVersion.id == version.id)
    )

    assert saved_material is not None
    assert saved_material.user_id == user.id
    assert saved_material.name == "Python 资料"
    assert saved_material.description is None
    assert saved_material.enabled is True
    assert saved_material.created_at is not None
    assert saved_material.updated_at is not None

    assert saved_version is not None
    assert saved_version.material_id == material.id
    assert saved_version.version_number == 1
    assert saved_version.normalized_format == MaterialFormat.MARKDOWN.value
    assert saved_version.parse_status == ParseStatus.UPLOADED.value
    assert saved_version.size_bytes == 128
    assert saved_version.content_hash == "a" * 64
    assert saved_version.source_metadata == {"line_start": 1, "line_end": 10}
    assert saved_version.parser_name is None
    assert saved_version.processed_at is None
    assert saved_version.uploaded_at is not None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalized_format", "docx"),
        ("parse_status", "SUCCESS"),
        ("version_number", 0),
        ("size_bytes", -1),
    ],
)
def test_material_version_rejects_invalid_database_values(
    db_session,
    field: str,
    value: object,
) -> None:
    user = _create_user(db_session, username=f"invalid-material-{field}")
    material = _create_material(db_session, user.id, name=f"约束-{field}")
    version = _create_version(db_session, material.id)
    setattr(version, field, value)
    db_session.add(version)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_material_version_supports_all_formats_and_statuses(db_session) -> None:
    user = _create_user(db_session, username="material-enum-owner")
    material = _create_material(db_session, user.id, name="格式状态测试")

    version_number = 1
    for material_format in MaterialFormat:
        version = _create_version(
            db_session,
            material.id,
            version_number=version_number,
            normalized_format=material_format.value,
        )
        version.original_filename = f"source-{version_number}"
        version_number += 1

    for parse_status in ParseStatus:
        version = _create_version(
            db_session,
            material.id,
            version_number=version_number,
            parse_status=parse_status.value,
        )
        version.original_filename = f"status-{version_number}"
        version_number += 1

    db_session.commit()

    formats = set(
        db_session.scalars(
            select(MaterialVersion.normalized_format).where(
                MaterialVersion.material_id == material.id
            )
        ).all()
    )
    statuses = set(
        db_session.scalars(
            select(MaterialVersion.parse_status).where(
                MaterialVersion.material_id == material.id
            )
        ).all()
    )

    assert formats == {item.value for item in MaterialFormat}
    assert statuses == {item.value for item in ParseStatus}


def test_version_number_is_unique_within_one_material(db_session) -> None:
    user = _create_user(db_session, username="material-version-owner")
    material = _create_material(db_session, user.id, name="版本测试")
    _create_version(db_session, material.id, version_number=1)
    db_session.commit()

    duplicate = _create_version(db_session, material.id, version_number=1)
    duplicate.original_filename = "python-copy.md"

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_version_number_is_allowed_for_different_materials(db_session) -> None:
    user = _create_user(
        db_session,
        username="material-independent-version-owner",
    )
    first = _create_material(db_session, user.id, name="第一份资料")
    second = _create_material(db_session, user.id, name="第二份资料")
    _create_version(db_session, first.id, version_number=1)
    _create_version(db_session, second.id, version_number=1)

    db_session.commit()

    assert db_session.query(MaterialVersion).count() == 2


def test_processing_and_failure_fields_are_nullable(db_session) -> None:
    user = _create_user(db_session, username="material-processing-owner")
    material = _create_material(db_session, user.id, name="处理字段测试")
    version = _create_version(
        db_session,
        material.id,
        parse_status=ParseStatus.FAILED.value,
    )
    version.parse_error_code = "PDF_TEXT_LAYER_MISSING"
    version.parse_error_message = "资料没有可提取的文本层"
    version.processed_at = utc_now()
    db_session.commit()

    saved = db_session.get(MaterialVersion, version.id)
    assert saved is not None
    assert saved.parse_error_code == "PDF_TEXT_LAYER_MISSING"
    assert saved.parse_error_message == "资料没有可提取的文本层"
    assert saved.processed_at is not None


def test_material_has_no_project_id_or_binary_content_column() -> None:
    material_columns = set(Material.__table__.columns.keys())
    version_columns = set(MaterialVersion.__table__.columns.keys())

    assert "project_id" not in material_columns
    assert "content" not in version_columns
    assert "file_bytes" not in version_columns