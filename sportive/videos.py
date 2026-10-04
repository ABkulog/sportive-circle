"""Videos on feed posts: one per post, up to a minute, kept as files next to the database.

Phones record MP4 (Android) or QuickTime .mov (iPhone), both "ISO media" files, so they're read without any
extra tools: the length comes from the file's own header, and the place it was filmed (phones save GPS
coordinates in it) is overwritten with zeros before it's kept. Videos aren't re-encoded, so a big one stays
big: each is capped, and all of them together have a quota (VIDEO_QUOTA_MB) so they can never fill the disk the
database lives on. Moving to a video service (like Cloudflare Stream) later only changes this file.
"""
import os
import re
import secrets
import struct

from flask import current_app

from .db import get_db

MAX_SECONDS = 60
MAX_VIDEO_MB = 60
DEFAULT_QUOTA_MB = 300  # all videos together (the disk also holds the database and its backups)
TYPES = {"isom", "iso2", "iso4", "iso5", "iso6", "mp41", "mp42", "avc1", "qt  ", "M4V ", "MSNV", "3gp4", "3gp5",
         "dash", "mmp4", "hvc1"}
# GPS in ISO 6709 form, as phones write it: "+47.6553-122.3035+012.345/"
LOCATION = re.compile(rb"[+-]\d{1,3}\.\d+[+-]\d{1,3}\.\d+(?:[+-]\d+\.\d+)?/")


class VideoError(ValueError):
    """A video that can't be posted, with a message for the person posting it."""


def folder():
    path = current_app.config.get("VIDEO_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(current_app.config["DATABASE"])), "videos")
    os.makedirs(path, exist_ok=True)
    return path


def _boxes(data, start, end):
    """(type, payload start, payload end) for each box between start and end."""
    at = start
    while at + 8 <= end:
        size, kind = struct.unpack(">I4s", data[at:at + 8])
        header = 8
        if size == 1 and at + 16 <= end:
            size = struct.unpack(">Q", data[at + 8:at + 16])[0]
            header = 16
        elif size == 0:
            size = end - at
        if size < header or at + size > end:
            return
        yield kind, at + header, at + size
        at += size


def duration_seconds(data):
    """The length of an MP4 / QuickTime video, from its movie header (mvhd); None if it can't be read."""
    for kind, start, end in _boxes(data, 0, len(data)):
        if kind != b"moov":
            continue
        for inner, istart, iend in _boxes(data, start, end):
            if inner == b"mvhd" and iend - istart >= 20:
                version = data[istart]
                if version == 1 and iend - istart >= 32:
                    timescale, duration = struct.unpack(">IQ", data[istart + 20:istart + 32])
                else:
                    timescale, duration = struct.unpack(">II", data[istart + 12:istart + 20])
                return duration / timescale if timescale else None
    return None


def is_iso_media(data):
    return len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12].decode("latin-1") in TYPES


def scrub_location(data):
    """Overwrite GPS coordinates with zeros (same length, so nothing else in the file moves)."""
    return LOCATION.sub(lambda m: re.sub(rb"\d", b"0", m.group(0)), data)


def used_mb():
    total = get_db().execute("SELECT COALESCE(SUM(size), 0) FROM post_videos").fetchone()[0]
    return total / (1024 * 1024)


def check_and_save(upload):
    """Check an uploaded video and keep it: (file name, size, seconds). Raises VideoError."""
    data = upload.read()
    if len(data) > MAX_VIDEO_MB * 1024 * 1024:
        raise VideoError(f"Videos can be up to {MAX_VIDEO_MB} MB. Try a shorter clip, or record in 1080p or less.")
    if not is_iso_media(data):
        raise VideoError("That video type isn't supported. Post an MP4 or a video from your phone's camera.")
    seconds = duration_seconds(data)
    if seconds is None:
        raise VideoError("We couldn't read that video. Try another one.")
    if seconds > MAX_SECONDS + 0.5:
        raise VideoError(f"Videos can be up to 1 minute. This one is {round(seconds)} seconds: trim it first.")
    quota = float(current_app.config.get("VIDEO_QUOTA_MB") or DEFAULT_QUOTA_MB)
    if used_mb() + len(data) / (1024 * 1024) > quota:
        current_app.logger.warning("Video space is full (%.0f MB of %.0f MB)", used_mb(), quota)
        raise VideoError("Video space is full right now. Post photos instead, and we'll make room soon.")
    name = secrets.token_urlsafe(18) + ".mp4"
    with open(os.path.join(folder(), name), "wb") as file:
        file.write(scrub_location(data))
    return name, len(data), seconds


def path_of(name):
    """The file for a stored video name (names are made here, but never trust a path from a database row)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.mp4", name or ""):
        return None
    return os.path.join(folder(), name)


def remove_files(names):
    for name in names:
        path = path_of(name)
        if path and os.path.exists(path):
            os.remove(path)
