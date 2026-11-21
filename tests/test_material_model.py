import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.material import Material, MaterialFormat, utc_now
from app.models.user import User


def _material(db_session, name="Notes") -> Material:
    user = db_session.scalar(select(User).where(User.username == "material-owner"))
    if user is None:
        user = User(username="material-owner", password_hash="test-password-hash")
        db_session.add(user)
        db_session.flush()
    material = Material(
        user_id=user.id, name=name, original_filename="notes.md",
        normalized_format="markdown", mime_type="text/markdown", size_bytes=20,
        content_hash="a" * 64, storage_object_key=f"{user.id}/{name}.md",
    )
    db_session.add(material)
    return material


def test_material_persists_file_and_parse_fields(db_session) -> None:
    material = _material(db_session)
    db_session.commit()
    db_session.refresh(material)
    assert material.id > 0
    assert material.parse_status == "UPLOADED"
    assert material.uploaded_at is not None
    assert material.updated_at is not None
    assert material.processed_at is None
    assert material.parsed_content_location is None
    assert list(MaterialFormat) == [MaterialFormat.MARKDOWN]


@pytest.mark.parametrize(("field", "value"), [
    ("normalized_format", "txt"), ("normalized_format", "text_pdf"),
    ("normalized_format", "docx"), ("parse_status", "SUCCESS"), ("size_bytes", -1),
])
def test_material_rejects_invalid_database_values(db_session, field, value) -> None:
    material = _material(db_session)
    setattr(material, field, value)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_content_can_be_two_independent_materials(db_session) -> None:
    first = _material(db_session, "first")
    second = _material(db_session, "second")
    db_session.commit()
    assert first.id != second.id
    assert first.content_hash == second.content_hash
    assert first.storage_object_key != second.storage_object_key
    first.parse_status = "FAILED"
    first.parse_error_code = "MATERIAL_CONTENT_EMPTY"
    first.parse_error_message = "material contains no text"
    first.processed_at = utc_now()
    db_session.commit()
    db_session.refresh(second)
    assert second.parse_status == "UPLOADED"
    assert second.parse_error_code is None