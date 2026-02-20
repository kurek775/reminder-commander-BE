from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_engine = None
_AsyncSessionLocal = None


def _get_session_factory() -> async_sessionmaker:
    global _engine, _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _engine = create_async_engine(settings.database_url, echo=False)
        _AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)
    return _AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
