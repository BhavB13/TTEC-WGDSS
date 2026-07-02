from sqlalchemy import create_engine

from app.core.config import settings


def _build_connect_args() -> dict[str, object]:
    if settings.DATABASE_URL.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _build_engine_options() -> dict[str, object]:
    if settings.DATABASE_URL.startswith("sqlite"):
        return {}
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_recycle": settings.DB_POOL_RECYCLE_SECONDS,
    }


engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    future=True,
    pool_pre_ping=True,
    connect_args=_build_connect_args(),
    **_build_engine_options(),
)
