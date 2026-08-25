from sqlalchemy.orm import Session

from app.models.material import Material, MaterialVersion, ParseStatus


def create_material_upload(
    db: Session,
    *,
    user_id: int,
    name: str,
    description: str | None,
    original_filename: str,
    normalized_format: str,
    mime_type: str,
    size_bytes: int,
    content_hash: str,
    storage_object_key: str,
) -> tuple[Material, MaterialVersion]:
    material = Material(
        user_id=user_id,
        name=name,
        description=description,
    )
    db.add(material)
    db.flush()

    version = MaterialVersion(
        material_id=material.id,
        version_number=1,
        original_filename=original_filename,
        normalized_format=normalized_format,
        mime_type=mime_type,
        size_bytes=size_bytes,
        content_hash=content_hash,
        storage_object_key=storage_object_key,
        parse_status=ParseStatus.UPLOADED.value,
    )
    db.add(version)
    db.commit()
    db.refresh(material)
    db.refresh(version)
    return material, version
