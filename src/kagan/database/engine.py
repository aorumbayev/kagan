"""Async SQLAlchemy engine setup for SQLModel."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel


async def create_db_engine(db_path: str | Path) -> AsyncEngine:
    """Create async SQLite engine with WAL mode."""
    db_path_str = str(db_path)
    if db_path_str == ":memory:":
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        db_path_path = Path(db_path_str)
        db_path_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")

    return engine


async def create_db_tables(engine: AsyncEngine) -> None:
    """Create all tables from SQLModel metadata."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def drop_db_tables(engine: AsyncEngine) -> None:
    """Drop all tables (for testing only)."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
