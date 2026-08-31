from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON
from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KnowledgeNodeStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        CheckConstraint(
            "length(title) BETWEEN 1 AND 160",
            name="ck_knowledge_nodes_title",
        ),
        CheckConstraint(
            "length(description) BETWEEN 1 AND 5000",
            name="ck_knowledge_nodes_description",
        ),
        CheckConstraint(
            "difficulty BETWEEN 1 AND 5",
            name="ck_knowledge_nodes_difficulty",
        ),
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','ARCHIVED')",
            name="ck_knowledge_nodes_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=KnowledgeNodeStatus.DRAFT.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class KnowledgeNodePrerequisite(Base):
    __tablename__ = "knowledge_node_prerequisites"
    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "prerequisite_node_id",
            name="uq_knowledge_node_prerequisites_edge",
        ),
        CheckConstraint(
            "node_id <> prerequisite_node_id",
            name="ck_knowledge_node_prerequisites_not_self",
        ),
        Index("ix_knowledge_node_prerequisites_node_id", "node_id"),
        Index(
            "ix_knowledge_node_prerequisites_prerequisite_node_id",
            "prerequisite_node_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id"), nullable=False
    )
    prerequisite_node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class KnowledgeNodeSource(Base):
    __tablename__ = "knowledge_node_sources"
    __table_args__ = (
        CheckConstraint(
            "block_index >= 0",
            name="ck_knowledge_node_sources_block_index",
        ),
        CheckConstraint(
            "line_start >= 1 AND line_end >= line_start",
            name="ck_knowledge_node_sources_line_range",
        ),
        Index("ix_knowledge_node_sources_node_id", "node_id"),
        Index(
            "ix_knowledge_node_sources_material_version_id",
            "material_version_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    node_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_nodes.id"), nullable=False
    )
    material_version_id: Mapped[int] = mapped_column(
        ForeignKey("material_versions.id"), nullable=False
    )
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    section_path: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    quote_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
