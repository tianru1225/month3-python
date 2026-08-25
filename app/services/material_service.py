from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.material import MaterialFormat, ParseStatus
from app.repositories.material_repository import create_material_upload
from app.schemas.material import MaterialUploadResponse

MATERIAL_STORAGE_DIR = Path("data/materials")
MATERIAL_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_UPLOAD_RULES: dict[str, tuple[MaterialFormat, frozenset[str]]] = {
    ".md": (
        MaterialFormat.MARKDOWN,
        frozenset({"text/markdown", "text/plain"}),
    ),
    ".markdown": (
        MaterialFormat.MARKDOWN,
        frozenset({"text/markdown", "text/plain"}),
    ),
    ".txt": (
        MaterialFormat.TXT,
        frozenset({"text/plain"}),
    ),
    ".pdf": (
        MaterialFormat.TEXT_PDF,
        frozenset({"application/pdf"}),
    ),
}


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _normalize_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or len(normalized) > 120:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "MATERIAL_NAME_INVALID",
            "material name must contain 1 to 120 characters",
        )
    return normalized


def _normalize_description(description: str | None) -> str | None:
    if description is None:
        return None
    normalized = description.strip()
    return normalized or None


def _validate_filename(filename: str) -> tuple[str, str]:
    if (
        not filename
        or filename != filename.strip()
        or len(filename) > 255
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or any(ord(character) < 32 or ord(character) == 127 for character in filename)
    ):
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "MATERIAL_FILENAME_INVALID",
            "invalid upload filename",
        )

    extension = Path(filename).suffix.lower()
    if extension not in _UPLOAD_RULES:
        raise _error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "MATERIAL_FORMAT_UNSUPPORTED",
            "unsupported material format",
        )
    return filename, extension


def _validate_content_type(extension: str, content_type: str) -> tuple[str, str]:
    normalized_content_type = content_type.split(";", 1)[0].strip().lower()
    material_format, allowed_content_types = _UPLOAD_RULES[extension]
    if normalized_content_type not in allowed_content_types:
        raise _error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "MATERIAL_MIME_INVALID",
            "file content type does not match its extension",
        )
    return material_format.value, normalized_content_type


def upload_material_or_raise(
    db: Session,
    *,
    user_id: int,
    name: str,
    description: str | None,
    filename: str,
    content_type: str,
    content: bytes,
) -> MaterialUploadResponse:
    normalized_name = _normalize_name(name)
    normalized_description = _normalize_description(description)
    original_filename, extension = _validate_filename(filename)
    normalized_format, normalized_content_type = _validate_content_type(
        extension,
        content_type,
    )

    if not content:
        raise _error(
            status.HTTP_400_BAD_REQUEST,
            "MATERIAL_FILE_EMPTY",
            "uploaded file is empty",
        )
    if len(content) > MATERIAL_MAX_UPLOAD_BYTES:
        raise _error(
            status.HTTP_413_CONTENT_TOO_LARGE, 
            "MATERIAL_FILE_TOO_LARGE",
            "uploaded file exceeds the 10 MiB limit",
        )

    storage_object_key = f"{user_id}/{uuid4().hex}{extension}"
    destination = MATERIAL_STORAGE_DIR / storage_object_key

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(content)
    except OSError as exc:
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "MATERIAL_STORAGE_ERROR",
            "material file could not be stored",
        ) from exc

    try:
        material, version = create_material_upload(
            db,
            user_id=user_id,
            name=normalized_name,
            description=normalized_description,
            original_filename=original_filename,
            normalized_format=normalized_format,
            mime_type=normalized_content_type,
            size_bytes=len(content),
            content_hash=sha256(content).hexdigest(),
            storage_object_key=storage_object_key,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "MATERIAL_DATABASE_ERROR",
            "material metadata could not be stored",
        ) from exc

    return MaterialUploadResponse(
        material_id=material.id,
        version_id=version.id,
        name=material.name,
        description=material.description,
        enabled=material.enabled,
        version_number=version.version_number,
        original_filename=version.original_filename,
        normalized_format=MaterialFormat(version.normalized_format),
        mime_type=version.mime_type,
        size_bytes=version.size_bytes,
        content_hash=version.content_hash,
        parse_status=ParseStatus(version.parse_status),
        uploaded_at=version.uploaded_at,
    )