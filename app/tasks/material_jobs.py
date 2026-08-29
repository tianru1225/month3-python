from app.db.session import SessionLocal
from app.models.material import ParseStatus
from app.repositories.material_repository import get_material_version
from app.services.material_service import process_material_version


def parse_material_version_job(version_id: int, job_id: str) -> str:
    with SessionLocal() as db:
        version = get_material_version(db, version_id=version_id)
        if version is None:
            return "ignored:not_found"
        if version.parse_job_id != job_id:
            return "ignored:stale_job"
        if version.parse_status != ParseStatus.QUEUED.value:
            return f"ignored:{version.parse_status.lower()}"

        process_material_version(db, version)
        return version.parse_status
