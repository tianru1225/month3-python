from pathlib import Path
import re

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeNodeSource
from app.models.learning_plan import LearningPlan
from app.models.learning_project import LearningProject
from app.models.material import Material, utc_now
from app.models.project_material import ProjectMaterialBinding
from app.repositories.material_repository import lock_material
from app.schemas.material_management import MaterialManagementItem, MaterialManagementPage
from app.services import material_service


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _lock_related_projects(db: Session, material_id: int) -> None:
    project_ids = select(ProjectMaterialBinding.project_id).where(
        ProjectMaterialBinding.material_id == material_id
    )
    # 与创建首个计划共用项目行锁，检查历史时不能并发出现新计划。
    list(db.scalars(
        select(LearningProject).where(LearningProject.id.in_(project_ids))
        .order_by(LearningProject.id).with_for_update()
    ))


def _blockers(db: Session, material: Material) -> list[str]:
    material_id = material.id
    reasons = []
    active_projects = list(db.scalars(
        select(ProjectMaterialBinding.project_id)
        .join(LearningProject, LearningProject.id == ProjectMaterialBinding.project_id)
        .where(
            ProjectMaterialBinding.material_id == material_id,
            ProjectMaterialBinding.unbound_at.is_(None),
            LearningProject.deleted_at.is_(None),
        ).distinct().order_by(ProjectMaterialBinding.project_id)
    ))
    if active_projects:
        names = ", ".join(f"#{value}" for value in active_projects)
        reasons.append(f"仍绑定在项目 {names}，请先从这些项目移除")
    if material.parse_status in {"QUEUED", "PARSING"}:
        reasons.append("资料正在排队或解析，请等待结束后刷新")
    if db.scalar(select(KnowledgeNodeSource.id).where(
        KnowledgeNodeSource.material_id == material_id
    ).limit(1)) is not None:
        reasons.append("已有知识来源引用，需保留原文与学习历史")
    # 当前计划 content 为自由 JSON，没有可靠的资料引用清单。
    # 历史绑定项目一旦有计划，就保守保留资料，不猜测它是否被用过。
    historical_projects = select(ProjectMaterialBinding.project_id).where(
        ProjectMaterialBinding.material_id == material_id
    )
    if db.scalar(select(LearningPlan.id).where(
        LearningPlan.project_id.in_(historical_projects)
    ).limit(1)) is not None:
        reasons.append("曾绑定的项目已有学习计划，当前无法证明无历史引用，暂不允许彻底删除")
    return reasons


def list_materials_for_management(
    db: Session, *, user_id: int, before_id: int | None, limit: int
) -> MaterialManagementPage:
    statement = select(Material).where(Material.user_id == user_id)
    if before_id is not None:
        statement = statement.where(Material.id < before_id)
    rows = list(db.scalars(statement.order_by(Material.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    return MaterialManagementPage(
        items=[
            MaterialManagementItem(
                material_id=item.id, name=item.name, created_at=item.uploaded_at,
                deletion_pending=item.deletion_started_at is not None,
                blockers=_blockers(db, item),
            )
            for item in page
        ],
        next_before_id=page[-1].id if len(rows) > limit else None,
    )


def _safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("invalid storage path")
    candidate = root / path
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("storage path escapes root")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symbolic links are not cleanup targets")
    if candidate.is_dir():
        raise ValueError("expected a file")
    return candidate


def _cleanup_paths(db: Session, material: Material) -> tuple[list[Path], Path]:
    root = material_service.MATERIAL_STORAGE_DIR.resolve()
    if re.fullmatch(
        rf"{material.user_id}/[0-9a-f]{{32}}\.(md|markdown)",
        material.storage_object_key,
    ) is None:
        raise ValueError("unsupported original file layout")
    shared = db.scalar(select(Material.id).where(
        Material.storage_object_key == material.storage_object_key,
        Material.id != material.id,
    ).limit(1))
    if shared is not None:
        raise ValueError("storage file is shared with another material")
    # 已有解析文件不重命名；按持久化路径清理，限定在本资料目录内。
    parsed = material.parsed_content_location or f"parsed/{material.id}/content.md"
    if re.fullmatch(rf"parsed/{material.id}/([0-9]+|content)\.md", parsed) is None:
        raise ValueError("unsupported parsed file layout")
    sources = str(Path(parsed).with_suffix(".sources.json"))
    metadata = material.source_metadata
    if metadata is not None and metadata.get("sources_path") not in (None, sources):
        raise ValueError("unsupported source map layout")
    paths = [_safe_path(root, relative) for relative in (
        material.storage_object_key, parsed, sources,
    )]
    marker = _safe_path(root, f"parsed/{material.id}/.cleanup-check")
    return sorted(set(paths)), marker.parent


def delete_material_or_raise(db: Session, *, material_id: int, user_id: int) -> None:
    try:
        material = lock_material(db, material_id=material_id, user_id=user_id)
        if material is None:
            raise _error(404, "MATERIAL_NOT_FOUND", "资料不存在或不属于当前用户")
        _lock_related_projects(db, material.id)
        reasons = _blockers(db, material)
        if reasons:
            raise _error(409, "MATERIAL_IN_USE", "；".join(reasons))
        try:
            _cleanup_paths(db, material)
        except ValueError as exc:
            raise _error(409, "MATERIAL_STORAGE_LAYOUT_INVALID",
                         "文件路径不符合当前存储规则，请先核对服务器记录") from exc
        if material.deletion_started_at is None:
            material.deletion_started_at = utc_now()
        # 先保存不可继续使用的事实，再进行不可回滚的文件操作。
        db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        # 串行化多个重试；第一次提交后退出的进程可以从这里恢复。
        material = lock_material(db, material_id=material_id, user_id=user_id)
        if material is None:
            return  # 另一个同用户请求已经完成清理。
        _lock_related_projects(db, material.id)
        reasons = _blockers(db, material)
        if reasons:
            raise _error(409, "MATERIAL_IN_USE", "；".join(reasons))
        paths, parsed_directory = _cleanup_paths(db, material)
        for path in paths:
            path.unlink(missing_ok=True)
        if parsed_directory.exists():
            parsed_directory.rmdir()  # 有未知文件就失败；不递归清掉其他内容。
        db.execute(delete(ProjectMaterialBinding).where(
            ProjectMaterialBinding.material_id == material.id
        ))
        db.delete(material)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except (OSError, ValueError, SQLAlchemyError) as exc:
        db.rollback()
        raise _error(
            503, "MATERIAL_DELETE_RETRY_REQUIRED",
            "清理尚未确认完成，资料已停止使用；请刷新管理列表并重试清理",
        ) from exc