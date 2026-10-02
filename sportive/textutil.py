"""Small text helpers for things people type."""
import re
import secrets
import unicodedata


def one_line(text):
    """Trim and squash all whitespace (including line breaks) into single spaces.

    For names and titles: they go into email subjects and calendar files, where a line break
    would break the format (and one bad title could stop everyone's reminder emails).
    """
    return " ".join((text or "").split())


# Count as letters but show as nothing (Hangul fillers, the blank Braille cell): a name of only these looks empty.
BLANK_LOOKING = set("\u3164\u115f\u1160\uffa0\u2800")
ZWJ = "\u200d"  # joins emoji into one picture (👩🏽‍🦱): kept, it can't disguise a name


def person_name(text):
    """A name as it should be shown: one line, without invisible characters (zero-width spaces, and
    right-to-left overrides that can make "Maya" display as someone else's name)."""
    visible = "".join(ch for ch in (text or "") if ch not in BLANK_LOOKING
                      and (ch == ZWJ or unicodedata.category(ch) not in ("Cf", "Cc")))
    return one_line(visible)


def initial(name):
    """The first letter for an avatar circle, uppercase. An emoji keeps its skin tone and joined parts
    (a code point alone can be half a character)."""
    name = (name or "").strip()
    if not name:
        return ""
    end = 1
    while end < len(name):
        ch = name[end]
        joined = name[end - 1] == ZWJ
        if ch == ZWJ or joined or unicodedata.category(ch) in ("Mn", "Me") or "\U0001F3FB" <= ch <= "\U0001F3FF" \
                or ch == "\ufe0f":
            end += 1
        else:
            break
    return name[:end].upper()


def fold(text):
    """For matching and sorting: lowercase without accents, so "Jose" finds "José" and "adam" sorts with "Adam"."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    # The Turkish dotless ı has no accent to strip: "yilmaz" should still find "Yılmaz".
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold().replace("ı", "i")


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


HANDLE_SITES = {"instagram": r"instagram\.com", "tiktok": r"tiktok\.com", "snapchat": r"snapchat\.com/add",
                "x_handle": r"(x|twitter)\.com"}


def social_handle(key, value):
    """A username as people really type or paste it: "@maya", "instagram.com/maya", or
    "https://www.instagram.com/maya/?hl=en" -> "maya"."""
    value = one_line(value).strip()
    site = HANDLE_SITES.get(key)
    if site:
        value = re.sub(rf"^(https?://)?(www\.|m\.)?{site}/", "", value, flags=re.I)
        value = value.split("?")[0].split("#")[0].strip("/").split("/")[0]
    return value.lstrip("@")


def is_number(text):
    """Plain digits 0-9 only. (str.isdigit() also says yes to "²" or "٣", which int() can't read: a 500.)"""
    return text.isascii() and text.isdigit()
