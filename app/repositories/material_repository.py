from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.material import Material, ParseStatus, utc_now
from app.core.material_state import transition_parse_status


def create_material_upload(
    db: Session, *, user_id: int, name: str, description: str | None,
    original_filename: str, normalized_format: str, mime_type: str,
    size_bytes: int, content_hash: str, storage_object_key: str,
) -> Material:
    material = Material(
        user_id=user_id, name=name, description=description,
        original_filename=original_filename, normalized_format=normalized_format,
        mime_type=mime_type, size_bytes=size_bytes, content_hash=content_hash,
        storage_object_key=storage_object_key, parse_status=ParseStatus.UPLOADED.value,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


def get_owned_material(
    db: Session, *, material_id: int, user_id: int, lock: bool = False,
) -> Material | None:
    statement = select(Material).where(
        Material.id == material_id, Material.user_id == user_id,
        Material.deletion_started_at.is_(None),
    ).execution_options(populate_existing=True)
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def mark_material_queued(
    db: Session,
    material: Material,
    *,
    job_id: str,
) -> None:
    transition_parse_status(material, ParseStatus.QUEUED)
    material.parse_job_id = job_id
    material.parser_name = None
    material.parser_version = None
    material.parse_error_code = None
    material.parse_error_message = None
    material.processed_at = None
    db.commit()
    db.refresh(material)


def restore_parse_queue_state(
    db: Session,
    material: Material,
    *,
    expected_job_id: str,
    parse_status: str,
    parse_job_id: str | None,
    parser_name: str | None,
    parser_version: str | None,
    parse_error_code: str | None,
    parse_error_message: str | None,
    processed_at: datetime | None,
) -> None:
    # Worker 已接手时不能把 PARSING 恢复成可删除的 UPLOADED/FAILED。
    lock_material(db, material_id=material.id)
    db.refresh(material)
    if material.parse_job_id != expected_job_id or material.parse_status != "QUEUED":
        db.rollback()
        return
    # 队列投递失败时的补偿恢复，不是业务状态转换，因此不走状态机。
    material.parse_status = parse_status
    material.parse_job_id = parse_job_id
    material.parser_name = parser_name
    material.parser_version = parser_version
    material.parse_error_code = parse_error_code
    material.parse_error_message = parse_error_message
    material.processed_at = processed_at
    db.commit()
    db.refresh(material)


def mark_material_parsing(db: Session, material: Material) -> None:
    transition_parse_status(material, ParseStatus.PARSING)
    db.commit()
    db.refresh(material)


def mark_material_ready(
    db: Session,
    material: Material,
    *,
    parser_name: str,
    parser_version: str,
    content_summary: str,
    parsed_content_location: str,
    source_metadata: dict,
) -> None:
    transition_parse_status(material, ParseStatus.READY)
    material.parser_name = parser_name
    material.parser_version = parser_version
    material.content_summary = content_summary
    material.parsed_content_location = parsed_content_location
    material.source_metadata = source_metadata
    material.parse_error_code = None
    material.parse_error_message = None
    material.processed_at = utc_now()
    db.commit()
    db.refresh(material)


def mark_material_failed(
    db: Session,
    material: Material,
    *,
    parser_name: str,
    parser_version: str,
    error_code: str,
    error_message: str,
) -> None:
    transition_parse_status(material, ParseStatus.FAILED)
    material.parser_name = parser_name
    material.parser_version = parser_version
    material.content_summary = None
    material.parsed_content_location = None
    material.source_metadata = None
    material.parse_error_code = error_code
    material.parse_error_message = error_message
    material.processed_at = utc_now()
    db.commit()
    db.refresh(material)


def list_ready_materials_for_user(db: Session, *, user_id: int) -> list[Material]:
    return list(db.scalars(
        select(Material).where(
            Material.user_id == user_id, Material.deletion_started_at.is_(None),
            Material.parse_status == ParseStatus.READY.value,
        ).order_by(Material.id)
    ))


def get_material_for_user(
    db: Session, *, material_id: int, user_id: int
) -> Material | None:
    return db.scalar(
        select(Material).where(
            Material.id == material_id,
            Material.user_id == user_id,
            Material.deletion_started_at.is_(None),
        ).with_for_update().execution_options(populate_existing=True)
    )



def lock_material(
    db: Session, *, material_id: int, user_id: int | None = None
) -> Material | None:
    statement = select(Material).where(Material.id == material_id)
    if user_id is not None:
        statement = statement.where(Material.user_id == user_id)
    return db.scalar(
        statement.with_for_update().execution_options(populate_existing=True)
    )