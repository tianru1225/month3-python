from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.deps.db import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services.user_service import create_user_or_raise, get_user_or_raise

router = APIRouter(prefix="/users", tags=["users"])

@router.post(
    "",
    response_model = UserResponse,
    status_code = status.HTTP_201_CREATED,
    summary = "创建用户",
    description="创建一个新用户。username或email已存在时返回USER_ALREADY_EXISTS",
    responses={
        201: {"description": "用户创建成功"},
        400: {"description": "用户名或邮箱已存在"}
    }
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    return create_user_or_raise(db,payload)

@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="查询用户",
    description="根据user_id查询用户。用户不存在时返回USER_NOT_FOUND",
    responses={
        200: {"description": "查询成功"},
        404: {"description": "用户不存在"}
    }
)
def get_user(user_id: int, db: Session = Depends(get_db)):
    return get_user_or_raise(db, user_id)