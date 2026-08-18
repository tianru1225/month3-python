from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_username_or_email(
    db: Session, username: str, email: str
) -> User | None:
    return (
        db.query(User)
        .filter((User.username == username) | (User.email == email))
        .first()
    )


def create_user(db: Session, *, username: str, email: str, password_hash: str) -> User:
    user = User(username=username, email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_identifier(db: Session, identifier: str) -> User | None:
    return (
        db.query(User)
        .filter((User.username == identifier) | (User.email == identifier))
        .first()
    )
