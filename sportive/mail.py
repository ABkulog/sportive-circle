"""Sending email (verification codes, reminders)."""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)


def send_email(to, subject, body):
    """Send an email. Returns False in local development, where nothing is actually sent."""
    cfg = current_app.config
    if not cfg.get("MAIL_SERVER"):
        if current_app.debug or current_app.testing:
            log.warning("DEV email (not sent) to %s: %s\n%s", to, subject, body)
            return False
        raise RuntimeError("MAIL_SERVER is not configured, so emails can't be sent.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"]) as smtp:
        smtp.starttls()
        smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        smtp.send_message(msg)
    return True
