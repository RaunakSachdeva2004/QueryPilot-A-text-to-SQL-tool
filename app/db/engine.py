"""
SQLAlchemy engine factories.

Two engines:
  - owner engine: for migrations, seeding, query_runs, checkpoints.
  - readonly engine: ONLY for executing generated SQL.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import get_settings


def get_owner_engine() -> Engine:
    """Return the owner/app database engine (synchronous)."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )


def get_readonly_engine() -> Engine:
    """Return the read-only database engine (synchronous)."""
    settings = get_settings()
    return create_engine(
        settings.readonly_database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
