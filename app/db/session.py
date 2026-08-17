from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def build_engine(database_url: str) -> Engine:
    normalized_url = database_url.strip()
    if not normalized_url:
        raise ValueError("DATABASE_URL must not be empty")
    connect_args = (
        {"check_same_thread": False} if normalized_url.startswith("sqlite") else {}
    )
    return create_engine(
        normalized_url,
        connect_args=connect_args,
        pool_pre_ping=True,
    )


engine = build_engine(settings.database_url.get_secret_value())

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
