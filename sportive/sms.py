"""Texts (SMS): optional, for people who'd rather get codes and game updates by text than by email.

Email stays required (the UW address is how we know someone is a UW student); a phone number is extra.
Nothing is ever texted unless the person typed their number, ticked the permission box, and confirmed the
number with a texted code. They can turn texts off (or remove the number) in Settings -> Texts, or reply STOP.

Sending uses Twilio (https://www.twilio.com). Set in Render -> Environment:
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM (the texting number, like +12065551234, or a
    Messaging Service id starting with MG).
Without them, texts are hidden on the live site; locally (debug/tests) texts are logged and codes shown on screen.
"""
import base64
import json
import logging
import re
import secrets
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from flask import current_app, flash, g

from .db import get_db
from .timeutil import from_db, now_local, to_db

log = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5
RESEND_WAIT = timedelta(seconds=60)
MAX_CODES_PER_DAY = 5    # code texts per person per day (texts cost money; stops abuse)
MAX_TEXTS_PER_DAY = 20   # update texts per person per day (and as many again for game changes/cancels/reminders)
INVITE_TEXTS_PER_SENDER = 3  # "You down?" texts from one person to another a day
IMPORTANT_KINDS = ("important", "reminder")  # game changed/canceled and reminders: never crowded out
MAX_CODES_PER_NUMBER = 3  # code texts to one number per day, whoever asks (texts to strangers cost money)
CONSENT = ("Text me reminders and updates about my games. Msg & data rates may apply. "
           "Reply STOP to stop, HELP for help.")
OPTED_OUT = 21610  # Twilio: this number replied STOP


def sms_configured():
    cfg = current_app.config
    return bool(cfg.get("TWILIO_ACCOUNT_SID") and cfg.get("TWILIO_AUTH_TOKEN") and cfg.get("TWILIO_FROM"))


def sms_available():
    """Offer texts? Only when a texting service is set up (or on a developer's laptop / in tests)."""
    return sms_configured() or current_app.debug or current_app.testing


def normalize_phone(raw):
    """"(206) 555-0142", "206.555.0142", "+1 206 555 0142" -> "+12065550142". None if it isn't a phone number.
    US numbers can be typed without +1; other countries need their + code."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+1") and len(digits) != 11:
        return None  # US/Canada numbers are exactly +1 and 10 digits
    if raw.startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] not in "01":
        return f"+1{digits}"
    return None


def pretty_phone(phone):
    """+12065550142 -> (206) 555-0142 (other countries stay as they are)."""
    if phone and phone.startswith("+1") and len(phone) == 12:
        return f"({phone[2:5]}) {phone[5:8]}-{phone[8:]}"
    return phone or ""


def masked_phone(phone):
    """+12065550142 -> (•••) •••-0142, for pages that remind you which number got the code."""
    return f"(•••) •••-{phone[-4:]}" if phone else ""


def _post_to_twilio(to, body):
    cfg = current_app.config
    sender = cfg["TWILIO_FROM"]
    fields = {"To": to, "Body": body, ("MessagingServiceSid" if sender.startswith("MG") else "From"): sender}
    request = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{cfg['TWILIO_ACCOUNT_SID']}/Messages.json",
        data=urllib.parse.urlencode(fields).encode(), method="POST")
    token = base64.b64encode(f"{cfg['TWILIO_ACCOUNT_SID']}:{cfg['TWILIO_AUTH_TOKEN']}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        detail = json.loads(error.read() or b"{}")
        raise SmsError(detail.get("code"), detail.get("message", str(error))) from None


class SmsError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def send_sms(to, body):
    """Send one text. Returns True if it went out, False in local development (logged instead)."""
    if not sms_configured():
        log.info("SMS (dev mode, not sent) to %s: %s", to, body)
        return False
    _post_to_twilio(to, body)
    return True


def _log(user_id, phone, kind, ok):
    get_db().execute("INSERT INTO sms_log (user_id, phone, kind, ok, created_at) VALUES (?, ?, ?, ?, ?)",
                     (user_id, phone, kind, 1 if ok else 0, to_db(now_local())))


def _sent_today(user_id, codes, kind=None):
    """Texts really sent in the last day (failed ones don't use up the allowance; checks on a number that's
    already taken do count as codes): codes, or updates. With `kind`,
    only that kind ("important" for game changed/canceled and reminders, "invite:<inviter id>" for "You down?")."""
    since = to_db(now_local() - timedelta(days=1))
    if kind in IMPORTANT_KINDS:
        which, args = "kind IN ('important', 'reminder')", ()
    elif kind is not None:
        which, args = "kind = ?", (kind,)
    elif codes:  # code texts that went out, and every check on a number someone else already uses
        which, args = "(kind = 'lookup' OR (kind = 'code' AND ok = 1))", ()
    else:  # ordinary updates: everything but codes and the important ones (those have their own allowance)
        which, args = "kind NOT IN ('code', 'lookup', 'important', 'reminder')", ()
    counted = "" if codes and kind is None else " AND ok = 1"  # (codes: `which` says which count)
    return get_db().execute(f"SELECT COUNT(*) FROM sms_log WHERE user_id = ? AND created_at >= ?{counted} AND {which}",
                            (user_id, since, *args)).fetchone()[0]


# ---------------------------------------------------------------- confirming a number

def code_wait(user):
    """Seconds until another code can be texted (0 = now)."""
    if not user["sms_sent_at"]:
        return 0
    left = from_db(user["sms_sent_at"]) + RESEND_WAIT - now_local()
    return max(0, int(left.total_seconds()) + 1) if left.total_seconds() > 0 else 0


def start_phone_check(user_id, phone):
    """Save the number (not confirmed yet) and text it a 6-digit code. Returns an error message or None."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user["phone"] == phone and code_wait(user):
        return f"We just texted a code. Wait {code_wait(user)} seconds to ask for another."
    if _sent_today(user_id, codes=True) >= MAX_CODES_PER_DAY:
        return "That's a lot of codes for one day. Try again tomorrow."
    since = to_db(now_local() - timedelta(days=1))
    if db.execute("SELECT COUNT(*) FROM sms_log WHERE phone = ? AND kind = 'code' AND created_at >= ?",
                  (phone, since)).fetchone()[0] >= MAX_CODES_PER_NUMBER:
        return "That number got a lot of codes today. Try again tomorrow."
    taken = db.execute("SELECT 1 FROM users WHERE phone = ? AND phone_verified = 1 AND id != ?",
                       (phone, user_id)).fetchone()
    if taken:
        # Costs the person asking one of their day's codes (so nobody can look numbers up for free), but isn't
        # a code to that number: it doesn't use up the real owner's codes.
        _log(user_id, phone, "lookup", False)
        db.commit()
        return "That number is already used by another account."
    code = f"{secrets.randbelow(10**6):06d}"
    db.execute("""UPDATE users SET phone = ?, phone_verified = 0, sms_code = ?, sms_code_expires = ?,
                  sms_code_attempts = 0, sms_sent_at = ? WHERE id = ?""",
               (phone, code, to_db(now_local() + CODE_TTL), to_db(now_local()), user_id))
    try:
        sent = send_sms(phone, f"Sportive Circle code: {code}. It expires in {CODE_TTL.seconds // 60} min. "
                               "Don't share it. Reply STOP to stop texts.")
    except Exception as error:
        _log(user_id, phone, "code", False)
        db.commit()
        log.exception("Couldn't text a code to user %s", user_id)
        return ("We couldn't text that number. Check it and try again."
                if getattr(error, "code", None) != OPTED_OUT else
                "That number replied STOP to our texts. Text START to our number to allow them again.")
    _log(user_id, phone, "code", True)
    db.commit()
    if not sent:
        flash(f"Dev mode (no text service set up): the texted code is {code}", "info")
    return None


def check_phone_code(user_id, code):
    """Returns None if the code is right (the number is confirmed and texts are on), else what went wrong."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user["phone"] or not user["sms_code"]:
        return "Ask for a code first."
    if user["sms_code_attempts"] >= MAX_CODE_ATTEMPTS:
        return "Too many wrong tries. Ask for a new code."
    if now_local() > from_db(user["sms_code_expires"]):
        return "That code expired. Ask for a new one."
    if not secrets.compare_digest(code.encode(), user["sms_code"].encode()):
        db.execute("UPDATE users SET sms_code_attempts = sms_code_attempts + 1 WHERE id = ?", (user_id,))
        db.commit()
        return "That texted code isn't right."
    # Only if nobody confirmed the same number in the meantime (two accounts can both ask for a code).
    confirmed = db.execute("""UPDATE users SET phone_verified = 1, sms_updates = 1, sms_consent_at = ?, sms_code = NULL,
                              sms_code_expires = NULL, sms_code_attempts = 0, sms_stopped_at = NULL
                              WHERE id = ? AND NOT EXISTS (
                                SELECT 1 FROM users other WHERE other.phone = users.phone AND other.phone_verified = 1
                                AND other.id != users.id)""", (to_db(now_local()), user_id)).rowcount
    db.commit()
    return None if confirmed else "That number is already used by another account."


def remove_phone(user_id):
    get_db().execute("""UPDATE users SET phone = '', phone_verified = 0, sms_updates = 0, sms_code = NULL,
                        sms_code_expires = NULL, sms_stopped_at = NULL WHERE id = ?""", (user_id,))
    get_db().commit()


# ---------------------------------------------------------------- updates

SMS_LIMIT = 160       # one text's worth of plain characters; longer (or any emoji) costs 2-3 texts
PREFIX = "Sportive Circle: "
PLAIN = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", "·": "-",
                       "→": "->", "\u00a0": " "})


def one_text(body):
    """Fit an update into one plain text: emoji dropped, accents and curly quotes made plain (José -> Jose),
    and the words shortened if needed. A link at the end is never cut."""
    body = unicodedata.normalize("NFKD", body.translate(PLAIN))
    body = "".join(ch for ch in body if 32 <= ord(ch) < 127 or ch == "\n")  # plain characters only
    body = re.sub(r"[ ]{2,}", " ", body).replace(" .", ".").strip()
    room = SMS_LIMIT - len(PREFIX)
    if len(body) <= room:
        return PREFIX + body
    link = re.search(r"\s(https?://\S+)$", body)
    words, tail = (body[:link.start()], " " + link.group(1)) if link else (body, "")
    keep = max(0, room - len(tail) - 3)
    return PREFIX + words[:keep].rstrip(" ,.:;-") + "..." + tail

def text_user(user_id, body, kind="update"):
    """Text someone an update, only if they confirmed their number and want texts. Never raises. The caller
    doesn't need to commit (this commits its own log line)."""
    if not sms_available():
        return False
    db = get_db()
    user = db.execute("SELECT phone, phone_verified, sms_updates, suspended FROM users WHERE id = ?",
                      (user_id,)).fetchone()
    if not user or not user["phone"] or not user["phone_verified"] or not user["sms_updates"] or user["suspended"]:
        return False
    if kind in IMPORTANT_KINDS:  # a game changed or canceled, a reminder: its own allowance, others can't use it up
        if _sent_today(user_id, codes=False, kind=kind) >= MAX_TEXTS_PER_DAY:
            return False
    elif _sent_today(user_id, codes=False) >= MAX_TEXTS_PER_DAY:
        return False
    elif kind.startswith("invite:") and _sent_today(user_id, codes=False, kind=kind) >= INVITE_TEXTS_PER_SENDER:
        return False  # one friend can't use up someone's texts with "You down?" over and over
    try:
        send_sms(user["phone"], one_text(body))
        ok = True
    except Exception as error:
        ok = False
        if getattr(error, "code", None) == OPTED_OUT:  # they replied STOP: respect it here too (Settings says so)
            db.execute("UPDATE users SET sms_updates = 0, sms_stopped_at = ? WHERE id = ?",
                       (to_db(now_local()), user_id))
        else:
            log.exception("Couldn't text user %s", user_id)
    _log(user_id, user["phone"], kind, ok)
    db.commit()
    return ok


def text_code(user_id, code, purpose):
    """A password-reset code by text too (for people who confirmed their number). Never raises."""
    db = get_db()
    user = db.execute("SELECT phone, phone_verified, sms_updates, suspended FROM users WHERE id = ?",
                      (user_id,)).fetchone()
    if not sms_available() or not user or not user["phone_verified"] or not user["sms_updates"] or user["suspended"]:
        return False  # texts turned off (or suspended): the email has the code
    if _sent_today(user_id, codes=True) >= MAX_CODES_PER_DAY:
        return False
    try:
        send_sms(user["phone"], f"Sportive Circle {purpose} code: {code}. It expires soon. Don't share it. Reply STOP to stop texts.")
        ok = True
    except Exception:
        ok = False
        log.exception("Couldn't text a %s code to user %s", purpose, user_id)
    _log(user_id, user["phone"], "code", ok)
    db.commit()
    return ok


# ---------------------------------------------------------------- texts that wait for the save

def queue_text(user_id, body, kind="update"):
    """Text someone once this request has saved everything (e.g. invites made inside an all-or-nothing
    database change: no network calls while the database is locked, and nothing sent if it's undone)."""
    g.setdefault("sms_queue", []).append((user_id, body, kind))


def drop_queued_texts():
    """The change was undone: don't send its texts."""
    g.pop("sms_queue", None)


def send_queued_texts(response):
    """after_request: send the texts this request queued (only if the page worked)."""
    queued = g.pop("sms_queue", None)
    if queued and response.status_code < 400:
        for user_id, body, kind in queued:
            text_user(user_id, body, kind)
    return response


def init_app(app):
    app.after_request(send_queued_texts)
