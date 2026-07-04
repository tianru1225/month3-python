from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate

def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User,user_id)

def get_user_by_username_or_email(db: Session, username:str, email:str) -> User | None:
    return db.query(User).filter((User.username == username) | (User.email == email)).first()

def create_user(db: Session, payload: UserCreate) -> User:
    user = User(username = payload.username,email = payload.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
