"""Small text helpers for things people type."""
import secrets
import unicodedata


def one_line(text):
    """Trim and squash all whitespace (including line breaks) into single spaces.

    For names and titles: they go into email subjects and calendar files, where a line break
    would break the format (and one bad title could stop everyone's reminder emails).
    """
    return " ".join((text or "").split())


def same_secret(sent, expected):
    """Constant-time comparison that works for any text. secrets.compare_digest raises TypeError on
    non-ASCII strings, so an emoji or accented letter in a form field must not reach it as str."""
    return secrets.compare_digest((sent or "").encode("utf-8"), (expected or "").encode("utf-8"))


def typed_code(text):
    """A 6-digit code as typed: full-width digits from Chinese/Japanese keyboards become 0-9."""
    return unicodedata.normalize("NFKC", text or "").strip()
