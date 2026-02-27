from urllib.parse import urlencode

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User


def get_google_auth_url() -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"


async def exchange_google_code(code: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        tokens = response.json()

    id_token_str = tokens.get("id_token", "")
    if not id_token_str:
        raise ValueError("No ID token in Google response")

    try:
        payload = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            audience=settings.google_client_id,
        )
    except Exception as exc:
        raise ValueError("Failed to verify ID token") from exc

    return {
        "google_id": payload["sub"],
        "email": payload["email"],
        "name": payload.get("name", ""),
        "picture": payload.get("picture", ""),
    }


async def upsert_user(db: AsyncSession, google_data: dict) -> User:
    result = await db.execute(
        select(User).where(User.google_id == google_data["google_id"])
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=google_data["email"],
            google_id=google_data["google_id"],
            display_name=google_data["name"],
            picture_url=google_data.get("picture"),
        )
        db.add(user)
    else:
        user.display_name = google_data["name"]
        user.picture_url = google_data.get("picture")
        db.add(user)

    await db.flush()
    await db.refresh(user)
    return user


def issue_tokens(user: User) -> dict:
    token_data = {"sub": str(user.id), "email": user.email}
    return {
        "access_token": create_access_token(token_data),
        "refresh_token": create_refresh_token(token_data),
        "token_type": "bearer",
    }
