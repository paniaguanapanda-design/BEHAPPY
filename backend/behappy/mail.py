"""Envio de correos."""
import os
import httpx
from .core import logger


def email_configured() -> bool:
    return bool(os.environ.get("RESEND_API_KEY") and os.environ.get("EMAIL_FROM"))


async def send_email(to: str, subject: str, text: str, html: str) -> bool:
    """Envia un email con Resend (https://resend.com). Devuelve False si falla."""
    if not email_configured():
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            r = await hc.post("https://api.resend.com/emails",
                              headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
                              json={"from": os.environ["EMAIL_FROM"], "to": [to], "subject": subject,
                                    "text": text, "html": html})
        if r.status_code >= 300:
            logger.warning("email no enviado: %s %s", r.status_code, r.text[:200])
        return r.status_code < 300
    except Exception as e:
        logger.warning("email no enviado: %s", e)
        return False


def _esc(v: str) -> str:
    import html
    return html.escape(v or "")
