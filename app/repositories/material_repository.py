from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.material import Material, MaterialVersion, ParseStatus, utc_now


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
    material = Material(user_id=user_id, name=name, description=description)
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


def get_material_version_for_user(
    db: Session,
    *,
    material_id: int,
    version_id: int,
    user_id: int,
) -> MaterialVersion | None:
    return db.scalar(
        select(MaterialVersion)
        .join(Material, Material.id == MaterialVersion.material_id)
        .where(
            MaterialVersion.id == version_id,
            MaterialVersion.material_id == material_id,
            Material.user_id == user_id,
        )
    )


def get_material_version(db: Session, *, version_id: int) -> MaterialVersion | None:
    return db.get(MaterialVersion, version_id)


def mark_version_queued(
    db: Session,
    version: MaterialVersion,
    *,
    job_id: str,
) -> None:
    version.parse_status = ParseStatus.QUEUED.value
    version.parse_job_id = job_id
    version.parser_name = None
    version.parser_version = None
    version.parse_error_code = None
    version.parse_error_message = None
    version.processed_at = None
    db.commit()
    db.refresh(version)


def restore_parse_queue_state(
    db: Session,
    version: MaterialVersion,
    *,
    parse_status: str,
    parse_job_id: str | None,
    parser_name: str | None,
    parser_version: str | None,
    parse_error_code: str | None,
    parse_error_message: str | None,
    processed_at: datetime | None,
) -> None:
    version.parse_status = parse_status
    version.parse_job_id = parse_job_id
    version.parser_name = parser_name
    version.parser_version = parser_version
    version.parse_error_code = parse_error_code
    version.parse_error_message = parse_error_message
    version.processed_at = processed_at
    db.commit()
    db.refresh(version)


def mark_version_parsing(db: Session, version: MaterialVersion) -> None:
    version.parse_status = ParseStatus.PARSING.value
    db.commit()
    db.refresh(version)


def mark_version_ready(
    db: Session,
    version: MaterialVersion,
    *,
    parser_name: str,
    parser_version: str,
    content_summary: str,
    parsed_content_location: str,
    source_metadata: dict,
) -> None:
    version.parse_status = ParseStatus.READY.value
    version.parser_name = parser_name
    version.parser_version = parser_version
    version.content_summary = content_summary
    version.parsed_content_location = parsed_content_location
    version.source_metadata = source_metadata
    version.parse_error_code = None
    version.parse_error_message = None
    version.processed_at = utc_now()
    db.commit()
    db.refresh(version)


def mark_version_failed(
    db: Session,
    version: MaterialVersion,
    *,
    parser_name: str,
    parser_version: str,
    error_code: str,
    error_message: str,
) -> None:
    version.parse_status = ParseStatus.FAILED.value
    version.parser_name = parser_name
    version.parser_version = parser_version
    version.content_summary = None
    version.parsed_content_location = None
    version.source_metadata = None
    version.parse_error_code = error_code
    version.parse_error_message = error_message
    version.processed_at = utc_now()
    db.commit()
    db.refresh(version)


def list_ready_versions_for_user(db: Session, *, user_id: int) -> list[MaterialVersion]:
    return list(
        db.scalars(
            select(MaterialVersion)
            .join(Material, Material.id == MaterialVersion.material_id)
            .where(
                Material.user_id == user_id,
                MaterialVersion.parse_status == ParseStatus.READY.value,
            )
            .order_by(MaterialVersion.id)
        )
    )


def get_material_for_user(
    db: Session, *, material_id: int, user_id: int
) -> Material | None:
    return db.scalar(
        select(Material).where(Material.id == material_id, Material.user_id == user_id)
    )
