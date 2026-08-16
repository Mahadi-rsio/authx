"""Test configuration.

Sets deterministic defaults so unit tests never target real services, and
bootstraps an isolated ``authx_test`` PostgreSQL database for integration
tests. Integration tests are skipped automatically when PostgreSQL is not
reachable (e.g. CI without ``docker compose up db``).
"""

import asyncio
import os

import pytest
from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.database.base import Base
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

BASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://authx:authx@localhost:5432/authx")
TEST_DB_NAME = "authx_test"
ADMIN_URL = BASE_URL.rsplit("/", 1)[0] + "/postgres"
TEST_DB_URL = BASE_URL.rsplit("/", 1)[0] + f"/{TEST_DB_NAME}"

_DB_AVAILABLE = False


def _create_test_database() -> None:
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)

    async def _run() -> None:
        async with engine.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DB_NAME}
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))

    asyncio.run(_run())
    asyncio.run(engine.dispose())


def pytest_configure(config: pytest.Config) -> None:
    global _DB_AVAILABLE
    try:
        _create_test_database()
        _DB_AVAILABLE = True
    except Exception:
        _DB_AVAILABLE = False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _DB_AVAILABLE:
        return
    skip = pytest.mark.skip(reason="PostgreSQL not available; skipping integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture()
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def db_session(db_engine):
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
