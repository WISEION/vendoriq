"""Outbound e-mail with a log fallback (brief §2: "SMTP from .env, fallback to log").

This module is deliberately just the transport seam: it knows how to hand a subject and a
body to SMTP, or to the log when ``SMTP_HOST`` is empty, and nothing about what the message
says. The AZ/EN templates phase 2G adds live in ``services/notifications.py`` — composing a
message and calling :func:`send` are kept apart so switching `SMTP_HOST` on is still the only
change needed to make the system actually deliver, and so a template can be unit-tested
without touching a socket.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from ..config import Settings
from ..errors import ApiError

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
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_tls:
                server.starttls()
            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # An unreachable or refusing relay is an operational condition, not a programming
        # error: without this, a vendor asking for a sign-in code got a raw 500 and the log
        # got a traceback per attempt (seen live on the compose rehearsal). The address of
        # the relay is for the log; the caller only learns delivery failed.
        logger.error("e-mail delivery failed to=%s via %s: %s", to, settings.smtp_host, exc)
        raise ApiError(
            503, "mail_unavailable", "The message could not be delivered. Try again shortly."
        ) from exc
    logger.info("e-mail sent to=%s subject=%s", to, subject)
    return True
