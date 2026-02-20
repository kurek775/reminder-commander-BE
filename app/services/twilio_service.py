from twilio.rest import Client

from app.core.config import settings


def send_whatsapp(to: str, body: str) -> str:
    """Send a WhatsApp message via Twilio.

    Args:
        to: Bare E.164 phone number, e.g. '+48123456789'
        body: Message text to send

    Returns:
        Twilio message SID
    """
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    msg = client.messages.create(
        from_=settings.twilio_whatsapp_from,
        body=body,
        to=f"whatsapp:{to}",
    )
    return msg.sid
