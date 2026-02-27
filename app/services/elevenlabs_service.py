import httpx

from app.core.config import settings


async def generate_audio(text: str) -> bytes:
    """Call ElevenLabs TTS API, return MP3 bytes."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}",
            headers={"xi-api-key": settings.elevenlabs_api_key},
            json={"text": text, "model_id": "eleven_turbo_v2_5"},
        )
        r.raise_for_status()
        return r.content
