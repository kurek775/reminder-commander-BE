"""C1: Twilio webhook signature validation dependency."""

import logging

from fastapi import HTTPException, Request, status
from twilio.request_validator import RequestValidator

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_twilio_signature(request: Request) -> None:
    """FastAPI dependency that validates the X-Twilio-Signature header.

    Skipped when twilio_auth_token is not configured (development without Twilio).
    """
    if not settings.twilio_auth_token:
        return

    validator = RequestValidator(settings.twilio_auth_token)

    signature = request.headers.get("X-Twilio-Signature", "")

    # Reconstruct URL using backend_url to handle TLS termination by reverse
    # proxies (ngrok). Twilio signs with the public https:// URL but the app
    # sees http:// behind the proxy.
    path = request.url.path
    query = str(request.url.query)
    url = settings.backend_url.rstrip("/") + path
    if query:
        url += "?" + query

    if request.method == "POST":
        form = await request.form()
        params = dict(form)
    else:
        params = {}

    if not validator.validate(url, params, signature):
        logger.warning("Invalid Twilio signature for %s", url)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )
