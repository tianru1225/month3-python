from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.material import MaterialVersion, ParseStatus
from app.repositories.material_repository import get_material_version, lock_material
from app.services.material_service import process_material_version


def parse_material_version_job(version_id: int, job_id: str) -> str:
    with SessionLocal() as db:
        material_id = db.scalar(
            select(MaterialVersion.material_id).where(MaterialVersion.id == version_id)
        )
        if material_id is None:
            return "ignored:not_found"
        material = lock_material(db, material_id=material_id)
        if material is None or material.deletion_started_at is not None:
            return "ignored:deleting"
        version = get_material_version(db, version_id=version_id)
        if version is None:
            return "ignored:not_found"
        if version.parse_job_id != job_id:
            return "ignored:stale_job"
        if version.parse_status != ParseStatus.QUEUED.value:
            return f"ignored:{version.parse_status.lower()}"

        process_material_version(db, version)
        return version.parse_status