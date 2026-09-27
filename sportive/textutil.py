"""Small text helpers for things people type."""


def one_line(text):
    """Trim and squash all whitespace (including line breaks) into single spaces.

    For names and titles: they go into email subjects and calendar files, where a line break
    would break the format (and one bad title could stop everyone's reminder emails).
    """
    return " ".join((text or "").split())
