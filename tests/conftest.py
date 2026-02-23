"""
Shared pytest fixtures for the Harmonia Risk API test suite.

Must be loaded before any test file — sets the test DB path env var
before any part of the app module is imported.
"""
import os
import pytest_asyncio
import aiosqlite

# Point at a dedicated test DB *before* importing app (settings reads env at import time)
os.environ.setdefault("HARMONIA_DATABASE_PATH", "test_harmonia.db")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database.db import init_db, DB_PATH


@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """Initialize schema and seed data once per test session."""
    await init_db()
    from data.seed_data import seed
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await seed(db)
    await db.close()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


@pytest_asyncio.fixture
async def client(setup_db):
    """Fresh AsyncClient for each test, sharing the seeded DB."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
