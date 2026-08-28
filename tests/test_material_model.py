import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.material import Material, MaterialFormat, MaterialVersion
from app.models.material import ParseStatus, utc_now
from app.models.user import User


def _create_user(db_session, username: str = "material-owner") -> User:
    user = User(username=username, password_hash="test-password-hash")
    db_session.add(user)
    db_session.flush()
    return user


def _create_material(db_session, user_id: int) -> Material:
    material = Material(user_id=user_id, name="Markdown 资料")
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
        storage_object_key="1/example.md",
        parse_status=parse_status,
    )
    db_session.add(version)
    return version


def test_material_and_version_persist_with_defaults(db_session) -> None:
    user = _create_user(db_session)
    material = _create_material(db_session, user.id)
    version = _create_version(db_session, material.id)
    db_session.commit()

    saved_material = db_session.scalar(
        select(Material).where(Material.id == material.id)
    )
    saved_version = db_session.scalar(
        select(MaterialVersion).where(MaterialVersion.id == version.id)
    )

    assert saved_material is not None
    assert saved_material.enabled is True
    assert saved_material.created_at is not None
    assert saved_material.updated_at is not None
    assert saved_version is not None
    assert saved_version.normalized_format == "markdown"
    assert saved_version.parse_status == "UPLOADED"
    assert saved_version.uploaded_at is not None
    assert saved_version.processed_at is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalized_format", "txt"),
        ("normalized_format", "text_pdf"),
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
    user = _create_user(db_session, username=f"invalid-{field}-{value}")
    material = _create_material(db_session, user.id)
    version = _create_version(db_session, material.id)
    setattr(version, field, value)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_only_markdown_format_is_available() -> None:
    assert list(MaterialFormat) == [MaterialFormat.MARKDOWN]


def test_version_number_is_unique_within_one_material(db_session) -> None:
    user = _create_user(db_session, username="material-version-owner")
    material = _create_material(db_session, user.id)
    _create_version(db_session, material.id)
    db_session.commit()

    _create_version(db_session, material.id)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_version_number_is_allowed_for_different_materials(db_session) -> None:
    user = _create_user(db_session, username="material-independent-owner")
    first = _create_material(db_session, user.id)
    second = _create_material(db_session, user.id)
    _create_version(db_session, first.id)
    _create_version(db_session, second.id)

    db_session.commit()
    assert db_session.query(MaterialVersion).count() == 2


def test_processing_fields_are_nullable(db_session) -> None:
    user = _create_user(db_session, username="material-processing-owner")
    material = _create_material(db_session, user.id)
    version = _create_version(
        db_session,
        material.id,
        parse_status=ParseStatus.FAILED.value,
    )
    version.parse_error_code = "MATERIAL_CONTENT_EMPTY"
    version.parse_error_message = "material contains no text"
    version.processed_at = utc_now()
    db_session.commit()

    saved = db_session.get(MaterialVersion, version.id)
    assert saved is not None
    assert saved.parse_error_code == "MATERIAL_CONTENT_EMPTY"
    assert saved.processed_at is not None
