import json
import re
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.material import MaterialFormat, MaterialVersion, ParseStatus
from app.parsers.markdown_parser import MarkdownParseError, parse_markdown
from app.repositories.material_repository import create_material_upload
from app.repositories.material_repository import get_material_version_for_user
from app.repositories.material_repository import mark_version_failed
from app.repositories.material_repository import mark_version_parsing
from app.repositories.material_repository import mark_version_ready
from app.schemas.material import MaterialParseResponse, MaterialUploadResponse

MATERIAL_STORAGE_DIR = Path("data/materials")
MATERIAL_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_PARSER_NAME = "markdown-token-parser"
_PARSER_VERSION = "markdown-it-py-3.0.0"

_UPLOAD_RULES: dict[str, frozenset[str]] = {
    ".md": frozenset({"text/markdown", "text/plain"}),
    ".markdown": frozenset({"text/markdown", "text/plain"}),
}


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _content_summary(content: str) -> str:
    return re.sub(r"\s+", " ", content.strip())[:200]


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
        or chr(92) in filename
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


def _validate_content_type(extension: str, content_type: str) -> str:
    normalized_content_type = content_type.split(";", 1)[0].strip().lower()
    if normalized_content_type not in _UPLOAD_RULES[extension]:
        raise _error(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "MATERIAL_MIME_INVALID",
            "file content type does not match its extension",
        )
    return normalized_content_type


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
    normalized_content_type = _validate_content_type(extension, content_type)

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
            normalized_format=MaterialFormat.MARKDOWN.value,
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


def _parse_response(version: MaterialVersion) -> MaterialParseResponse:
    return MaterialParseResponse(
        material_id=version.material_id,
        version_id=version.id,
        version_number=version.version_number,
        original_filename=version.original_filename,
        normalized_format=MaterialFormat(version.normalized_format),
        parse_status=ParseStatus(version.parse_status),
        parser_name=version.parser_name,
        parser_version=version.parser_version,
        content_summary=version.content_summary,
        parsed_content_location=version.parsed_content_location,
        source_metadata=version.source_metadata,
        parse_error_code=version.parse_error_code,
        parse_error_message=version.parse_error_message,
        processed_at=version.processed_at,
    )


def parse_material_version_or_raise(
    db: Session,
    *,
    user_id: int,
    material_id: int,
    version_id: int,
) -> MaterialParseResponse:
    version = get_material_version_for_user(
        db,
        material_id=material_id,
        version_id=version_id,
        user_id=user_id,
    )
    if version is None:
        raise _error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_VERSION_NOT_FOUND",
            "material version not found",
        )

    if version.parse_status == ParseStatus.READY.value:
        return _parse_response(version)
    if version.parse_status not in {
        ParseStatus.UPLOADED.value,
        ParseStatus.FAILED.value,
    }:
        raise _error(
            status.HTTP_409_CONFLICT,
            "MATERIAL_PARSE_NOT_ALLOWED",
            "material version cannot be parsed in its current state",
        )

    mark_version_parsing(db, version)
    parsed_path = (
        MATERIAL_STORAGE_DIR / "parsed" / str(material_id) / f"{version_id}.md"
    )
    sources_path = parsed_path.with_suffix(".sources.json")

    try:
        source_path = MATERIAL_STORAGE_DIR / version.storage_object_key
        if not source_path.is_file():
            raise MarkdownParseError(
                "MATERIAL_SOURCE_NOT_FOUND",
                "material source file not found",
            )

        document = parse_markdown(source_path.read_bytes())
        parsed_path.parent.mkdir(parents=True, exist_ok=True)
        parsed_path.write_text(document.text, encoding="utf-8")
        source_metadata = {
            "kind": "markdown",
            "line_count": document.line_count,
            "headings": document.headings,
            "sources_path": f"parsed/{material_id}/{version_id}.sources.json",
        }
        source_map = {
            "material_version_id": version.id,
            "normalized_format": MaterialFormat.MARKDOWN.value,
            "parser_name": _PARSER_NAME,
            "parser_version": _PARSER_VERSION,
            "blocks": document.blocks,
        }
        sources_path.write_text(
            json.dumps(source_map, ensure_ascii=False),
            encoding="utf-8",
        )
        mark_version_ready(
            db,
            version,
            parser_name=_PARSER_NAME,
            parser_version=_PARSER_VERSION,
            content_summary=_content_summary(document.text),
            parsed_content_location=f"parsed/{material_id}/{version_id}.md",
            source_metadata=source_metadata,
        )
    except MarkdownParseError as exc:
        parsed_path.unlink(missing_ok=True)
        sources_path.unlink(missing_ok=True)
        mark_version_failed(
            db,
            version,
            parser_name=_PARSER_NAME,
            parser_version=_PARSER_VERSION,
            error_code=exc.code,
            error_message=exc.message,
        )
    except Exception as exc:
        parsed_path.unlink(missing_ok=True)
        sources_path.unlink(missing_ok=True)
        mark_version_failed(
            db,
            version,
            parser_name=_PARSER_NAME,
            parser_version=_PARSER_VERSION,
            error_code="MATERIAL_PARSE_ERROR",
            error_message="material could not be parsed",
        )
        raise _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "MATERIAL_PARSE_ERROR",
            "material could not be parsed",
        ) from exc

    return _parse_response(version)