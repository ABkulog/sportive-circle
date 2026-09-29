"""Small text helpers for things people type."""
import secrets
import unicodedata


def one_line(text):
    """Trim and squash all whitespace (including line breaks) into single spaces.

    For names and titles: they go into email subjects and calendar files, where a line break
    would break the format (and one bad title could stop everyone's reminder emails).
    """
    return " ".join((text or "").split())


def person_name(text):
    """A name as it should be shown: one line, without invisible characters (zero-width spaces, and
    right-to-left overrides that can make "Maya" display as someone else's name)."""
    visible = "".join(ch for ch in (text or "") if unicodedata.category(ch) not in ("Cf", "Cc"))
    return one_line(visible)


def has_a_letter(text):
    return any(unicodedata.category(ch).startswith("L") for ch in text)


def multi_line(text):
    """Trim text that may have line breaks (notes, bios, messages), with every line break as a plain \\n.
    Browsers send \\r\\n, which would count twice toward length limits and break calendar files."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def same_secret(sent, expected):
    """Constant-time comparison that works for any text. secrets.compare_digest raises TypeError on
    non-ASCII strings, so an emoji or accented letter in a form field must not reach it as str."""
    return secrets.compare_digest((sent or "").encode("utf-8"), (expected or "").encode("utf-8"))


def typed_code(text):
    """A 6-digit code as typed: full-width digits from Chinese/Japanese keyboards become 0-9."""
    return unicodedata.normalize("NFKC", text or "").strip()
