"""Async SQLAlchemy engine/session setup for the ingestion pipeline.

Separate from backend/services/db.py (the main app's SQLite datastore) —
this pipeline targets its own PostgreSQL database via asyncpg, configured
with the INGESTION_DATABASE_URL env var so it never collides with the
main app's DB config.

Expected URL form: postgresql+asyncpg://user:password@host:port/dbname
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

INGESTION_DATABASE_URL = os.getenv(
    "INGESTION_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/job_ingestion",
)


class Base(DeclarativeBase):
    """Declarative base for all ingestion-pipeline models."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(INGESTION_DATABASE_URL, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def init_db() -> None:
    """Create all tables. Call once at startup / from a migration script."""
    from backend.ingestion import models  # noqa: F401  (register models on Base)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    if _engine is not None:
        await _engine.dispose()
