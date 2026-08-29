from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectMaterialBinding(Base):
    __tablename__ = "project_material_bindings"
    __table_args__ = (
        Index(
            "uq_project_material_bindings_active",
            "project_id",
            "material_id",
            unique=True,
            postgresql_where=text("unbound_at IS NULL"),
            sqlite_where=text("unbound_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("learning_projects.id"),
        nullable=False,
        index=True,
    )
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id"),
        nullable=False,
        index=True,
    )
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    unbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
