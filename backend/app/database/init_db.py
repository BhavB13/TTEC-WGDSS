from __future__ import annotations

import logging

from app.database.engine import engine
from app.models import Base

logger = logging.getLogger(__name__)


def initialize_database() -> None:
    """Create missing database tables for local/dev environments."""

    logger.info("Ensuring database tables exist")
    Base.metadata.create_all(bind=engine)
