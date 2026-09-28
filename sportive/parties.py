"""Parties: play with your friends.

"Party up" on a game: pick friends, and each gets a notice ("You down?") while their spot is held for
30 minutes. If you're not in the game yet, you join at the same time, so a whole group gets in at once.
Yes takes the held spot; No frees it for someone else.

Team vs team: the host's party is team 1. Another group "challenges" them by claiming team 2 the same
way (the leader joins and holds spots for their friends).
"""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .events import event_title, get_event, spots_left, try_join
from .invites import HOLD_TIME, held_spots, my_invite, now_param, team_counts
from .notifications import notify
from .social import is_blocked_between
from .timeutil import fmt_when, from_db, now_local, to_db

bp = Blueprint("parties", __name__)

MAX_PARTY = 10  # friends one person can invite to a game at once


def invitable_friends(event_id, me):
    """My friends who aren't in this game and haven't been invited to it yet (blocked people aren't friends)."""
    return get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f
           JOIN users u ON u.id = CASE WHEN f.requester_id = :me THEN f.addressee_id ELSE f.requester_id END
           WHERE (f.requester_id = :me OR f.addressee_id = :me) AND f.status = 'accepted'
             AND u.suspended = 0
             AND u.id NOT IN (SELECT user_id FROM rsvps WHERE event_id = :event)
             AND u.id NOT IN (SELECT guest_id FROM invites WHERE event_id = :event AND status = 'pending')
           ORDER BY u.full_name""", {"me": me, "event": event_id}).fetchall()


def party_plan(event):
    """What "Party up" means for me in this game: (team, joining_now, problem).

    team is None for regular games; joining_now = I'm not in yet and join together with my party.
    """
    me = g.user["id"]
    if event["cancelled"] or from_db(event["ends_at"]) < now_local():
        return None, False, "This game is over."
    if is_blocked_between(me, event["host_id"]):
        return None, False, "You can't join this game."
    mine = get_db().execute("SELECT team FROM rsvps WHERE event_id = ? AND user_id = ?",
                            (event["id"], me)).fetchone()
    if event["team_size"]:
        if mine:
            return mine["team"], False, None
        if team_counts(event["id"])[2] == 0 and held_spots(event["id"], team=2) == 0:
            return 2, True, None  # a challenge: my group becomes team 2
        return None, False, "Both teams are taken. Ask a player to invite you."
    if mine:
        return None, False, None
    if event["is_private"] and my_invite(event["id"], me) is None:
        return None, False, "This game is private. Join with the password first, then invite friends."
    return None, True, None


def room_for(event, team, me):
    """Spots my party can use right now: open spots (plus my own held spot), or what's left on my team."""
    if team is not None:
        taken = team_counts(event["id"])[team] + held_spots(event["id"], team=team, except_user=me)
        return max(event["team_size"] - taken, 0)
    left = spots_left(get_event(event["id"]))  # fresh counts
    if left is None:
        return None
    own_hold = held_spots(event["id"]) - held_spots(event["id"], except_user=me)
    return left + own_hold


@bp.route("/events/<int:event_id>/party", methods=("GET", "POST"))
@login_required
def party_up(event_id):
    event = get_event(event_id)
    me = g.user["id"]
    team, joining_now, problem = party_plan(event)
    if problem:
        flash(problem, "error")
        return redirect(url_for("events.detail", event_id=event_id))
    friends = invitable_friends(event_id, me)
    if request.method == "POST":
        allowed = {friend["id"] for friend in friends}
        chosen = list(dict.fromkeys(int(value) for value in request.form.getlist("friend") if value.isdigit()))
        if not chosen:
            flash("Pick at least one friend.", "error")
        elif any(friend_id not in allowed for friend_id in chosen):
            flash("You can only invite your friends who aren't in this game yet.", "error")
        elif len(chosen) > MAX_PARTY:
            flash(f"You can invite up to {MAX_PARTY} friends at once.", "error")
        else:
            error = send_party(event, chosen, team, joining_now)
            if error is None:
                flash(f"Invites sent. Their spot{'s are' if len(chosen) > 1 else ' is'} held for 30 minutes.",
                      "celebrate")
                return redirect(url_for("events.detail", event_id=event_id))
            flash(error, "error")
    return render_template("events/party.html", event=event, friends=friends, team=team, joining_now=joining_now,
                           room=room_for(event, team, me), challenge=joining_now and team == 2)


def send_party(event, chosen, team, joining_now):
    """Join (if needed) and hold a spot for each chosen friend, all or nothing. Returns an error or None."""
    db = get_db()
    me = g.user["id"]
    db.commit()
    db.execute("BEGIN IMMEDIATE")  # nobody else can grab spots between the check and the invites
    try:
        room = room_for(event, team, me)
        needed = len(chosen) + (1 if joining_now else 0)
        if room is not None and needed > room:
            db.rollback()
            for_friends = room - (1 if joining_now else 0)
            if for_friends <= 0:
                return "Sorry, there's no room for a party in this game."
            return f"Only {for_friends} spot{'s' if for_friends != 1 else ''} left for friends."
        title, first = event_title(event), g.user["full_name"].split()[0]
        if joining_now:
            db.execute("INSERT INTO rsvps (event_id, user_id, created_at, team) VALUES (?, ?, ?, ?)",
                       (event["id"], me, now_param(), team))
            mine = my_invite(event["id"], me)
            if mine:  # I was invited myself: that invite is answered now
                db.execute("UPDATE invites SET status = 'accepted' WHERE id = ?", (mine["id"],))
                notify(mine["inviter_id"], "invites", f"{first} is in for {title}.",
                       url_for("events.detail", event_id=event["id"]))
        expires = to_db(now_local() + HOLD_TIME)
        for friend_id in chosen:
            db.execute("""INSERT OR REPLACE INTO invites (event_id, inviter_id, guest_id, team, status, created_at, expires_at)
                          VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
                       (event["id"], me, friend_id, team, now_param(), expires))
            notify(friend_id, "invites", f"{first} wants you in {title} ({fmt_when(event['starts_at'])}). You down?",
                   url_for("events.detail", event_id=event["id"]))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return None


@bp.route("/events/<int:event_id>/invite/answer", methods=("POST",))
@login_required
def answer_invite(event_id):
    """'You down?' Yes takes the held spot; No frees it for someone else."""
    event = get_event(event_id)
    invite = my_invite(event_id, g.user["id"])
    if invite is None:
        flash("That invite isn't open anymore.", "info")
    elif request.form.get("answer") == "yes":
        joined, message = try_join(event)
        flash(message, "celebrate" if joined else "error")
    else:
        db = get_db()
        db.execute("UPDATE invites SET status = 'declined' WHERE id = ?", (invite["id"],))
        notify(invite["inviter_id"], "invites",
               f"{g.user['full_name'].split()[0]} can't make {event_title(event)}.",
               url_for("events.detail", event_id=event_id))
        db.commit()
        flash("No worries. Your spot is free for someone else.", "info")
    return redirect(url_for("events.detail", event_id=event_id))


@bp.route("/events/<int:event_id>/invite/<int:guest_id>/cancel", methods=("POST",))
@login_required
def cancel_invite(event_id, guest_id):
    """Take back an invite you sent (frees the held spot)."""
    db = get_db()
    cur = db.execute("""UPDATE invites SET status = 'canceled'
                        WHERE event_id = ? AND guest_id = ? AND inviter_id = ? AND status = 'pending'""",
                     (event_id, guest_id, g.user["id"]))
    db.commit()
    if not cur.rowcount:
        abort(404)
    flash("Invite canceled.", "info")
    return redirect(url_for("events.detail", event_id=event_id))


def can_party_up(event):
    """For templates: show "Party up" on this game?"""
    return g.get("user") is not None and party_plan(event)[2] is None
