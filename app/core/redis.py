"""M28: Centralized Redis connection dependency."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis

from app.core.config import settings


def _create_redis() -> aioredis.Redis:
    return aioredis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        db=0,
    )


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    r = _create_redis()
    try:
        yield r
    finally:
        await r.aclose()


@asynccontextmanager
async def redis_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Context manager for use outside of FastAPI dependency injection (e.g. worker tasks)."""
    r = _create_redis()
    try:
        yield r
    finally:
        await r.aclose()
