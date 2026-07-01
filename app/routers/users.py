from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy.orm import Session
from app.deps.db import get_db
from app.models.user import User
from app.schemas.user import UserCreate,UserResponse
router = APIRouter(prefix="/users",tags=["users"])
@router.post(
    "",
    response_model = UserResponse,
    status_code = status.HTTP_201_CREATED,
    responses = {400: {"description":"用户名或邮箱已存在"}},
)
def creaete_user(payload: UserCreate,db:Session = Depends(get_db)):
    existing=(
        db.query(User)
        .filter((User.username==payload.username)|(User.email == payload.email))
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code = 400,
            detail={"code":"USER_ALREADY_EXISTS","message":"username or email already exists"},
            )
    user = User(username=payload.username,email=payload.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
@router.get(
    "/{user_id}",
    response_model = UserResponse,
    responses = {404:{"description":"用户不存在"}},
)
def get_user(user_id: int,db:Session = Depends(get_db)):
    user = db.get(User,user_id)
    if user is None:
        raise HTTPException(
            status_code = status.HTTP_404_NOT_FOUND,
            detail = {
            "code":"USER_NOT_FOUND",
            "message":f"user {user_id} not found",
            },
        )
    return user