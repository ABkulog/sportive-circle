"""Admin → Clean up test data: posts, replies, clubs and club updates that look like keyboard mashing
("ajsghd", "askdgkahjslhd…"), listed with a box to tick, so an admin can wipe them before real people see the app.
Nothing is deleted without being ticked. "Show everything" lists all of it, for a full reset before a launch."""
import re

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .db import get_db
from .moderation import admin_required
from .videos import remove_files

bp = Blueprint("cleanup", __name__)

CONSONANT_RUN = re.compile(r"[bcdfghjklmnpqrstvwxz]{5,}", re.I)
LONG_WORD = re.compile(r"[a-z]{18,}", re.I)


def looks_like_junk(*texts):
    """True for keyboard mashing: 5+ consonants in a row ("jsghd") or one word of 18+ letters."""
    return any(text and (CONSONANT_RUN.search(text) or LONG_WORD.search(text)) for text in texts)


def candidates(everything=False):
    db = get_db()
    keep = (lambda *texts: True) if everything else looks_like_junk
    posts = [row for row in db.execute(
        """SELECT p.id, p.body, p.created_at, u.full_name, c.name AS club_name FROM posts p
           JOIN users u ON u.id = p.author_id LEFT JOIN clubs c ON c.id = p.club_id ORDER BY p.id DESC""")
        if keep(row["body"], row["club_name"])]
    replies = [row for row in db.execute(
        """SELECT r.id, r.body, r.created_at, u.full_name FROM post_replies r JOIN users u ON u.id = r.author_id
           ORDER BY r.id DESC""") if keep(row["body"])]
    clubs = [row for row in db.execute("SELECT id, name, description, status, created_at FROM clubs ORDER BY id DESC")
             if keep(row["name"], row["description"])]
    club_posts = [row for row in db.execute(
        """SELECT cp.id, cp.body, cp.created_at, c.name AS club_name FROM club_posts cp JOIN clubs c ON c.id = cp.club_id
           ORDER BY cp.id DESC""") if keep(row["body"])]
    return {"posts": posts, "replies": replies, "clubs": clubs, "club_posts": club_posts}


@bp.route("/admin/cleanup", methods=("GET", "POST"))
@admin_required
def cleanup():
    if request.method == "POST":
        db = get_db()
        ids = {kind: [int(i) for i in request.form.getlist(kind) if i.isdigit()]
               for kind in ("posts", "replies", "clubs", "club_posts")}
        files = []
        for post_id in ids["posts"]:
            files += [row[0] for row in db.execute("SELECT filename FROM post_videos WHERE post_id = ?", (post_id,))]
            db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        for reply_id in ids["replies"]:
            db.execute("DELETE FROM post_replies WHERE id = ?", (reply_id,))
        for club_post_id in ids["club_posts"]:
            db.execute("DELETE FROM club_posts WHERE id = ?", (club_post_id,))
        for club_id in ids["clubs"]:  # a junk club's games go with it (they'd otherwise lose their club)
            files += [row[0] for row in db.execute(
                "SELECT v.filename FROM post_videos v JOIN posts p ON p.id = v.post_id WHERE p.club_id = ?", (club_id,))]
            db.execute("DELETE FROM events WHERE club_id = ?", (club_id,))
            db.execute("DELETE FROM clubs WHERE id = ?", (club_id,))
        db.commit()
        remove_files(files)
        deleted = sum(len(v) for v in ids.values())
        flash(f"Deleted {deleted} item{'s' if deleted != 1 else ''}." if deleted else "Nothing was ticked.", "info")
        return redirect(url_for("cleanup.cleanup", all=request.args.get("all")))
    everything = request.args.get("all") == "1"
    return render_template("moderation/cleanup.html", found=candidates(everything), everything=everything)
