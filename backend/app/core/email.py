"""Transactional email via Resend. Send failures are logged, never raised —
callers (password reset) must not leak email delivery problems to the
client, since that would help an attacker enumerate accounts.
"""

from __future__ import annotations

import logging

import resend

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    settings = get_settings()
    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send(
            {
                "from": settings.resend_from_email,
                "to": [to_email],
                "subject": "Reset your DocIntel password",
                "html": (
                    f"<p>Someone requested a password reset for this account.</p>"
                    f'<p><a href="{reset_link}">Click here to reset your password</a>. '
                    f"This link expires in {settings.password_reset_expire_minutes} minutes.</p>"
                    f"<p>If you didn't request this, you can safely ignore this email.</p>"
                ),
            }
        )
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)
