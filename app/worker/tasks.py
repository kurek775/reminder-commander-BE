import logging

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="ping")
def ping() -> str:
    logger.info("Ping task executed")
    return "pong"
