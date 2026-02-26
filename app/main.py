import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.dashboard import router as dashboard_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.interactions import router as interactions_router
from app.api.v1.routes.rules import router as rules_router
from app.api.v1.routes.sheets import router as sheets_router
from app.api.v1.routes.voice import router as voice_router
from app.api.v1.routes.warlord import router as warlord_router
from app.api.v1.routes.webhook import router as webhook_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware
from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info("Reminder Commander API starting up", extra={"env": settings.app_env})
    yield
    logger.info("Reminder Commander API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Reminder Commander API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(sheets_router, prefix="/api/v1")
    app.include_router(rules_router, prefix="/api/v1")
    app.include_router(webhook_router, prefix="/api/v1")
    app.include_router(voice_router, prefix="/api/v1")
    app.include_router(warlord_router, prefix="/api/v1")
    app.include_router(interactions_router, prefix="/api/v1")

    return app


app = create_app()
