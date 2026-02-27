import os

from cryptography.fernet import Fernet

# Set test env vars BEFORE importing app (settings are read at import time)
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-min-32-chars!!")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/auth/google/callback")
os.environ.setdefault("GOOGLE_SHEETS_REDIRECT_URI", "http://localhost:8000/api/v1/sheets/callback")
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
# Disable Twilio signature validation in tests
os.environ["TWILIO_AUTH_TOKEN"] = ""
os.environ["TWILIO_ACCOUNT_SID"] = ""

import pytest
from httpx import ASGITransport, AsyncClient


class MockRedis:
    """Unified mock Redis for all tests."""

    def __init__(self, store: dict | None = None):
        self.store = store or {}

    async def get(self, key: str):
        return self.store.get(key)

    async def getdel(self, key: str):
        return self.store.pop(key, None)

    async def setex(self, key: str, ttl: int, value):
        self.store[key] = value

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def aclose(self):
        pass
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import create_access_token
from app.db.base import get_db
from app.main import app
from app.models.base import Base

# Import all models so SQLAlchemy metadata is fully populated
from app.models import interaction_log, sheet_integration, tracker_rule  # noqa: F401
from app.models.user import User

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncSession:
    TestingSession = async_sessionmaker(db_engine, expire_on_commit=False)
    async with TestingSession() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email="test@example.com",
        google_id="google_test_123",
        display_name="Test User",
        picture_url="https://example.com/pic.jpg",
    )
    db_session.add(user)
    await db_session.flush()  # visible in session but not permanently committed
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict:
    token = create_access_token({"sub": str(test_user.id), "email": test_user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def db_client(db_session: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Origin": "http://localhost:4200"},
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Origin": "http://localhost:4200"},
    ) as ac:
        yield ac
