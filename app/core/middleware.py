"""M12: Request ID middleware for request tracing (pure ASGI)."""

import uuid
from typing import Any, Callable

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """Pure ASGI middleware that adds a request ID to every HTTP response.

    Unlike BaseHTTPMiddleware, this does not wrap the ``receive`` channel,
    so downstream code (dependencies, Form() params) can read the request
    body without ``Stream consumed`` errors.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract existing header or generate a new request ID.
        raw_headers: list[tuple[bytes, bytes]] = scope.get("headers", [])
        request_id = ""
        header_lower = REQUEST_ID_HEADER.lower().encode()
        for name, value in raw_headers:
            if name == header_lower:
                request_id = value.decode()
                break
        if not request_id:
            request_id = str(uuid.uuid4())

        # Store in scope state so Request.state.request_id works downstream.
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        async def send_with_request_id(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((header_lower, request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_request_id)
