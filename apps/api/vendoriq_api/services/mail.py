"""Outbound e-mail with a log fallback (brief §2: "SMTP from .env, fallback to log").

Templates and the AZ/EN bodies are phase 2G. What exists now is the seam: everything that
notifies a person goes through :func:`send`, so switching `SMTP_HOST` on is the only change
needed to make the system actually deliver.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import Settings

logger = logging.getLogger("vendoriq.mail")


def send(settings: Settings, *, to: str, subject: str, body: str) -> bool:
    """Return True when the message left the process; False when it only reached the log."""
    if not settings.smtp_host:
        logger.info("e-mail (not sent, SMTP_HOST empty) to=%s subject=%s\n%s", to, subject, body)
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_tls:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)
    logger.info("e-mail sent to=%s subject=%s", to, subject)
    return True
