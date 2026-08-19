from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_username(
    db: Session, username: str
) -> User | None:
    return (
        db.query(User)
        .filter(User.username == username)
        .first()
    )


def create_user(db: Session, *, username: str, password_hash: str) -> User:
    user = User(username=username,  password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
