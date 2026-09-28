"""Sending email (verification codes, reminders)."""
import logging
import smtplib
from email.message import EmailMessage

import click
from flask import current_app, render_template
from flask.cli import with_appcontext

log = logging.getLogger(__name__)


def send_email(to, subject, body, html=None):
    """Send an email (plain text, plus the designed HTML version when given).
    Returns False in local development, where nothing is actually sent."""
    cfg = current_app.config
    if current_app.testing:
        # Tests read what would have been sent from app.extensions["outbox"].
        current_app.extensions.setdefault("outbox", []).append({"to": to, "subject": subject, "body": body,
                                                                "html": html})
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
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"]) as smtp:
        smtp.starttls()
        smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        smtp.send_message(msg)
    return True


def compose(subject, heading, lines, code=None, after=(), button=None, reason=None, preheader=None):
    """A friendly email in the app's design: (plain text, HTML), with the same words in both.

    lines/after: short paragraphs before/after the code. button: (label, url). reason: why they got it.
    """
    site = current_app.config["PUBLIC_URL"].rstrip("/")
    text = [heading, ""]
    text += [line + "\n" for line in lines]
    if code:
        text += [f"Your code: {code}", ""]
    text += [line + "\n" for line in after]
    if button:
        text += [f"{button[0]}: {button[1]}", ""]
    text += ["Go Dawgs! 💜💛", "The Sportive Circle team", "", "--"]
    if reason:
        text.append(reason)
    text.append("Sportive Circle is a student project for UW Huskies, not an official University of Washington service.")
    text.append(site)
    html = render_template("emails/message.html", subject=subject, heading=heading, lines=lines, code=code,
                           after=after, button=button, reason=reason, preheader=preheader, site=site,
                           site_name=site.replace("https://", "").replace("http://", ""))
    return "\n".join(text), html


def send_designed(to, subject, heading, lines, **options):
    """compose() + send_email(): the way every email in the app is sent."""
    text, html = compose(subject, heading, lines, **options)
    return send_email(to, subject, text, html=html)


def failure_reason(error):
    """A short, safe explanation of why an email didn't go out (never includes passwords or server replies)."""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        # The code tells them apart: 535 = wrong username/key, 525 = the email service blocked this server's IP.
        return f"the email service rejected our login, error {error.smtp_code} (check MAIL_USERNAME and MAIL_PASSWORD)"
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


def describe_settings(cfg):
    """Lines describing the email settings without revealing the key (safe to screenshot)."""
    user, key = cfg.get("MAIL_USERNAME") or "", cfg.get("MAIL_PASSWORD") or ""
    lines = [f"MAIL_SERVER    {cfg.get('MAIL_SERVER') or '(missing)'}:{cfg.get('MAIL_PORT')}",
             f"MAIL_FROM      {cfg.get('MAIL_FROM') or '(missing: using MAIL_USERNAME)'}"]
    note = "" if user.endswith("@smtp-brevo.com") else "   <- with Brevo this should end in @smtp-brevo.com"
    lines.append(f"MAIL_USERNAME  {user or '(missing)'}{note}")
    if key.startswith("xsmtpsib-"):
        shape = "looks like a Brevo SMTP key"
    elif key.startswith("xkeysib-"):
        shape = "this is a Brevo API key, not an SMTP key: generate an SMTP key instead"
    elif key:
        shape = "doesn't start with xsmtpsib- (a Brevo SMTP key does)"
    else:
        shape = "missing"
    lines.append(f"MAIL_PASSWORD  {len(key)} characters, {shape}")
    return lines


@click.command("check-email")
@click.argument("to", required=False)
@with_appcontext
def check_email_command(to):
    """Test the email settings: log in to the email service, and optionally send a test email.

        flask --app wsgi check-email                 # just test the login
        flask --app wsgi check-email you@uw.edu      # also send a test email
    """
    cfg = current_app.config
    for line in describe_settings(cfg):
        click.echo(line)
    if not cfg.get("MAIL_SERVER"):
        click.echo("No MAIL_SERVER set, so emails can't be sent.")
        return
    try:
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=20) as smtp:
            smtp.starttls()
            smtp.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        click.echo("LOGIN OK: the email service accepted the username and key.")
    except smtplib.SMTPResponseException as error:
        reply = error.smtp_error.decode(errors="replace") if isinstance(error.smtp_error, bytes) else str(error.smtp_error)
        click.echo(f"LOGIN REFUSED: {error.smtp_code} {reply}")
        return
    except OSError as error:
        click.echo(f"COULDN'T CONNECT: {error}")
        return
    if to:
        send_designed(to, "Sportive Circle test email", "It works! 🎉",
                      ["Emails from Sportive Circle can be sent. This is what they look like."],
                      reason="You're getting this because an admin tested the email settings.")
        click.echo(f"TEST EMAIL SENT to {to} (check Junk too).")
