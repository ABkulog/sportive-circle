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

import click
from flask import current_app
from flask.cli import with_appcontext

from .timeutil import now_local

log = logging.getLogger(__name__)

KEEP = 7  # days of copies
STALE_LOCK_SECONDS = 600  # a lock this old was left by a crash mid-copy


def backup_folder():
    return current_app.config.get("BACKUP_DIR") or os.path.join(
        os.path.dirname(os.path.abspath(current_app.config["DATABASE"])), "backups")


def make_backup(force=False):
    """Copy the database to today's backup file (unless it's there already). Returns its path, or None."""
    database = current_app.config["DATABASE"]
    if database == ":memory:" or not os.path.exists(database):
        return None
    folder = backup_folder()
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, f"sportive-{now_local():%Y-%m-%d}.db")
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


def backup_round(app):
    """Called from the background loop. Never raises."""
    try:
        with app.app_context():
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
