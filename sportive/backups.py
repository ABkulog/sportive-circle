"""Daily copies of the database, so a bad change or a broken file doesn't lose everyone's data.

Once a day the app copies the database to <database folder>/backups/sportive-YYYY-MM-DD.db (next to it on the
same disk) and keeps the newest KEEP copies. It runs in the same background loop as reminders (reminders.py), so it
needs nothing set up. SQLite's own backup copies a consistent snapshot even while people are using the site.

    flask --app wsgi backup      # make one now (e.g. before a risky change)

These copies live on the same disk, so also keep Render's disk snapshots on and copy one off the server now and then.
"""
import logging
import os
import sqlite3
import time
from datetime import timedelta

import click
from flask import current_app
from flask.cli import with_appcontext

from .db import get_db
from .timeutil import now_local, to_db

log = logging.getLogger(__name__)

KEEP = 7  # days of copies
STALE_LOCK_SECONDS = 600  # a lock this old was left by a crash mid-copy


def backup_folder():
    return current_app.config.get("BACKUP_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(current_app.config["DATABASE"])), "backups")


def _today_target():
    return os.path.join(backup_folder(), f"sportive-{now_local():%Y-%m-%d}.db")


def make_backup(force=False):
    """Copy the database to today's backup file (unless it's there already). Returns its path, or None."""
    database = current_app.config["DATABASE"]
    if database == ":memory:" or not os.path.exists(database):
        return None
    folder = backup_folder()
    os.makedirs(folder, exist_ok=True)
    target = _today_target()
    if os.path.exists(target) and not force:
        return None
    lock = target + ".lock"
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) > STALE_LOCK_SECONDS:
        log.warning("Removing a backup lock left by a crash: %s", lock)  # a copy takes seconds, not minutes
        os.remove(lock)
    try:  # the site runs as 2 copies: only one of them makes today's backup
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        if force:
            log.warning("Another backup is running right now (%s); try again in a minute.", lock)
        return None
    try:
        partial = target + ".partial"
        source, copy = sqlite3.connect(database), sqlite3.connect(partial)
        try:
            source.backup(copy)
            copy.execute("PRAGMA journal_mode = DELETE")  # one plain file (the live database uses WAL)
        finally:
            copy.close()
            source.close()
        for leftover in (partial + "-wal", partial + "-shm"):  # SQLite's side files from the copy
            if os.path.exists(leftover):
                os.remove(leftover)
        os.replace(partial, target)  # a half-written copy never looks like a real one
        remove_old_backups(folder)
        return target
    finally:
        os.remove(lock)


def remove_old_backups(folder):
    copies = sorted(name for name in os.listdir(folder) if name.startswith("sportive-") and name.endswith(".db"))
    for name in copies[:-KEEP]:
        os.remove(os.path.join(folder, name))


# Records only kept for a limit or a short window: (table, time column, days to keep). People's messages,
# games, reports and suggestions are never removed here.
EXPIRE = [("notices", "created_at", 90),         # the bell shows the last 30 days
          ("sms_log", "created_at", 30),         # daily text limits look back 1 day
          ("email_codes", "sent_at", 7),         # daily code limit looks back 1 day
          ("club_join_emails", "sent_at", 7),    # one email a day per person per club
          ("password_tries", "first_try", 7),    # 10 tries an hour
          ("login_failures", "failed_at", 7),    # 15-minute lockouts
          ("change_alerts", "sent_at", 7)]       # "Changed" emails: 3 a day per game per player


def clean_up_old_records():
    """Delete what's past its window, so the database (and each backup) doesn't grow forever. Returns rows removed."""
    db = get_db()
    removed = 0
    for table, column, days in EXPIRE:
        removed += db.execute(f"DELETE FROM {table} WHERE {column} < ?",
                              (to_db(now_local() - timedelta(days=days)),)).rowcount
    # Reactions whose message is gone (a deleted account or game took it): never shown, so tidy them away.
    removed += db.execute("""DELETE FROM message_reactions
                             WHERE (kind = 'dm' AND message_id NOT IN (SELECT id FROM direct_messages))
                                OR (kind = 'game' AND message_id NOT IN (SELECT id FROM event_messages))""").rowcount
    db.commit()
    return removed


def backup_round(app):
    """Called from the background loop: once a day, tidy up and back up. Never raises."""
    try:
        with app.app_context():
            if not os.path.exists(_today_target()):  # the first round of the day
                removed = clean_up_old_records()
                if removed:
                    log.info("Removed %d expired record(s).", removed)
            path = make_backup()
        if path:
            log.info("Backed up the database to %s", path)
    except Exception:
        log.exception("Couldn't back up the database")


@click.command("backup")
@with_appcontext
def backup_command():
    path = make_backup(force=True)
    click.echo(f"Saved {path}" if path else "Nothing to back up (no database file).")
