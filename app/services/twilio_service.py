from functools import lru_cache

from twilio.rest import Client

from app.core.config import settings


@lru_cache(maxsize=1)
def _get_client() -> Client:
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def make_voice_call(to: str, twiml_url: str, status_callback: str) -> str:
    """Initiate a Twilio voice call.

    Args:
        to: E.164 phone number to call, e.g. '+48123456789'
        twiml_url: URL Twilio will fetch for TwiML instructions
        status_callback: URL Twilio will POST call status updates to

    Returns:
        Twilio call SID
    """
    call = _get_client().calls.create(
        to=to,
        from_=settings.twilio_voice_from,
        url=twiml_url,
        status_callback=status_callback,
        status_callback_method="POST",
    )
    return call.sid


def send_whatsapp(to: str, body: str) -> str:
    """Send a WhatsApp message via Twilio.

    Args:
        to: Bare E.164 phone number, e.g. '+48123456789'
        body: Message text to send

    Returns:
        Twilio message SID
    """
    msg = _get_client().messages.create(
        from_=settings.twilio_whatsapp_from,
        body=body,
        to=f"whatsapp:{to}",
    )
    return msg.sid
