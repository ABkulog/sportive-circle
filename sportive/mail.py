"""Sending email (verification codes, reminders)."""
import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

log = logging.getLogger(__name__)


def send_email(to, subject, body):
    """Send an email. Returns False in local development, where nothing is actually sent."""
    cfg = current_app.config
    if current_app.testing:
        # Tests read what would have been sent from app.extensions["outbox"].
        current_app.extensions.setdefault("outbox", []).append({"to": to, "subject": subject, "body": body})
    if not cfg.get("MAIL_SERVER"):
        if current_app.debug or current_app.testing:
            log.warning("DEV email (not sent) to %s: %s\n%s", to, subject, body)
            return False
        raise RuntimeError("MAIL_SERVER is not configured, so emails can't be sent.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("MAIL_FROM") or f"Sportive Circle <{cfg['MAIL_USERNAME']}>"
    msg["To"] = to
    msg.set_content(body)
    with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"]) as smtp:
        smtp.starttls()
        smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        smtp.send_message(msg)
    return True


def failure_reason(error):
    """A short, safe explanation of why an email didn't go out (never includes passwords or server replies)."""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return "the email service rejected our login (check MAIL_USERNAME and MAIL_PASSWORD)"
    if isinstance(error, smtplib.SMTPSenderRefused):
        return "the email service didn't accept our sender address (check MAIL_FROM)"
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return "that address can't receive email"
    if isinstance(error, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, ConnectionError, TimeoutError,
                          OSError)) and not isinstance(error, smtplib.SMTPResponseException):
        return "we couldn't reach the email service (check MAIL_SERVER and MAIL_PORT)"
    if isinstance(error, smtplib.SMTPResponseException):
        return f"the email service answered with error {error.smtp_code}"
    if isinstance(error, RuntimeError):
        return "email isn't set up on this server yet (MAIL_SERVER is missing)"
    return "an unexpected email error"
