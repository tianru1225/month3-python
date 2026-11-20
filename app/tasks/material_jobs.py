from app.db.session import SessionLocal
from app.models.material import ParseStatus
from app.repositories.material_repository import lock_material
from app.services.material_service import process_material


def parse_material_job(material_id: int, job_id: str) -> str:
    with SessionLocal() as db:
        material = lock_material(db, material_id=material_id)
        if material is None:
            return "ignored:not_found"
        if material.deletion_started_at is not None:
            return "ignored:deleting"
        if material.parse_job_id != job_id:
            return "ignored:stale_job"
        if material.parse_status != ParseStatus.QUEUED.value:
            return f"ignored:{material.parse_status.lower()}"
        process_material(db, material)
        return material.parse_status