from sqlalchemy import create_engine

from app.core.config import settings


def _build_connect_args() -> dict[str, object]:
    if settings.DATABASE_URL.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    future=True,
    pool_pre_ping=True,
    connect_args=_build_connect_args(),
)
