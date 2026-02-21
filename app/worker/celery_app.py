from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "reminder_commander",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "check-and-send-reminders": {
            "task": "check_and_send_reminders",
            "schedule": 60.0,
        },
        "scan-warlord-sheets": {
            "task": "scan_warlord_sheets",
            "schedule": 60.0,
        },
    },
)
