import json
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.material import MaterialFormat, MaterialVersion
from app.repositories.project_material_repository import (
    list_ready_versions_for_project,
)


def _ready_required_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "MATERIAL_READY_REQUIRED",
            "message": "at least one ready material is required",
        },
    )


def _has_valid_output(
    version: MaterialVersion,
    *,
    storage_dir: Path,
) -> bool:
    if not version.parsed_content_location or version.source_metadata is None:
        return False

    parsed_path = storage_dir / version.parsed_content_location
    sources_path = parsed_path.with_suffix(".sources.json")
    try:
        parsed_text = parsed_path.read_text(encoding="utf-8")
        source_map = json.loads(sources_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False

    if not parsed_text.strip() or not isinstance(source_map, dict):
        return False

    return (
        source_map.get("material_version_id") == version.id
        and source_map.get("normalized_format") == MaterialFormat.MARKDOWN.value
        and isinstance(source_map.get("blocks"), list)
    )


def require_ready_materials_or_raise(
    db: Session,
    *,
    project_id: int,
    user_id: int,
    storage_dir: Path,
) -> list[MaterialVersion]:
    ready_versions = list_ready_versions_for_project(
        db,
        project_id=project_id,
        user_id=user_id,
    )
    usable_versions = [
        version
        for version in ready_versions
        if _has_valid_output(version, storage_dir=storage_dir)
    ]
    if not usable_versions:
        raise _ready_required_error()
    return usable_versions
