"""Shared fixtures for Deplyx backend tests."""

import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.base import Base

# Use an in-memory SQLite for tests (fast, no external deps)
TEST_DB_URL = "sqlite+aiosqlite:///./test.db"

engine_test = create_async_engine(TEST_DB_URL, echo=False)
TestSession = sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_db() -> AsyncGenerator[None, None]:
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        yield session


def make_token(email: str = "admin@deplyx.io", role: str = "Admin") -> str:
    return create_access_token(subject=email, role=role)


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token('admin@deplyx.io', 'Admin')}"}


@pytest.fixture
def viewer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token('viewer@deplyx.io', 'Viewer')}"}
