"""M28: Centralized Redis connection dependency."""

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
