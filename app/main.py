import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.rules import router as rules_router
from app.api.v1.routes.sheets import router as sheets_router
from app.api.v1.routes.webhook import router as webhook_router
from app.core.config import settings
from app.core.logging import setup_logging

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(sheets_router, prefix="/api/v1")
    app.include_router(rules_router, prefix="/api/v1")
    app.include_router(webhook_router, prefix="/api/v1")

    return app


app = create_app()
