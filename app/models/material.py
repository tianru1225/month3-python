from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class MaterialFormat(str, Enum):
    MARKDOWN = "markdown"
    TXT = "txt"
    TEXT_PDF = "text_pdf"


class ParseStatus(str, Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PARSING = "PARSING"
    READY = "READY"
    FAILED = "FAILED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class MaterialVersion(Base):
    __tablename__ = "material_versions"
    __table_args__ = (
        UniqueConstraint(
            "material_id",
            "version_number",
            name="uq_material_versions_material_version",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_material_versions_version_number",
        ),
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_material_versions_size_bytes",
        ),
        CheckConstraint(
            "normalized_format IN ('markdown','txt','text_pdf')",
            name="ck_material_versions_format",
        ),
        CheckConstraint(
            "parse_status IN ('UPLOADED','QUEUED','PARSING','READY','FAILED')",
            name="ck_material_versions_parse_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_format: Mapped[str] = mapped_column(String(20), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    parser_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parse_status: Mapped[str] = mapped_column(
        String(20),
        default=ParseStatus.UPLOADED.value,
        nullable=False,
    )
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_content_location: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    source_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parse_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parse_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
