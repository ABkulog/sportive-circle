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
from .textutil import one_line
from .timeutil import fmt_when, from_db, now_local, to_db

bp = Blueprint("parties", __name__)

MAX_PARTY = 10  # friends one person can invite to a game at once
MAX_NOTE = 150  # "this is my roommate": the note for the host of a private game


def invitable_friends(event_id, me):
    """My friends who aren't in this game and haven't been invited to it yet (blocked people aren't friends)."""
    return get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f
           JOIN users u ON u.id = CASE WHEN f.requester_id = :me THEN f.addressee_id ELSE f.requester_id END
           WHERE (f.requester_id = :me OR f.addressee_id = :me) AND f.status = 'accepted'
             AND u.suspended = 0
             AND u.id NOT IN (SELECT user_id FROM rsvps WHERE event_id = :event)
             AND u.id NOT IN (SELECT guest_id FROM invites WHERE event_id = :event AND status IN ('pending', 'requested'))
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
    invite = None if mine else my_invite(event["id"], me)
    if event["team_size"]:
        if mine:
            return mine["team"], False, None
        if invite:
            return invite["team"], True, None  # join the team I was invited to, and bring friends
        if event["is_private"]:
            return None, False, "This game is private. Ask the host to invite you."
        if team_counts(event["id"])[2] == 0 and held_spots(event["id"], team=2) == 0:
            return 2, True, None  # a challenge: my group becomes team 2
        return None, False, "Both teams are taken. Ask a player to invite you."
    if mine:
        return None, False, None
    if event["is_private"] and invite is None:
        return None, False, "This game is private. Join with the password first, then invite friends."
    return None, True, None


def needs_host_ok(event):
    """In a private game, the host decides who gets in: friends other players bring need their yes."""
    return bool(event["is_private"]) and event["host_id"] != g.user["id"]


def room_for(event, team, me):
    """Spots my party can use right now: open spots (plus my own held spot, if `me`), or what's left on a team."""
    if team is not None:
        taken = team_counts(event["id"])[team] + held_spots(event["id"], team=team, except_user=me)
        return max(event["team_size"] - taken, 0)
    left = spots_left(get_event(event["id"]))  # fresh counts
    if left is None or me is None:
        return left
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
            note = one_line(request.form.get("note"))[:MAX_NOTE]
            error = send_party(event, chosen, team, joining_now, note)
            if error is None:
                if needs_host_ok(event):
                    flash(f"Asked {event['host_name'].split()[0]}. Your friends get the invite once they say yes.",
                          "success")
                else:
                    flash(f"Invites sent. Their spot{'s are' if len(chosen) > 1 else ' is'} held for 30 minutes.",
                          "celebrate")
                return redirect(url_for("events.detail", event_id=event_id))
            flash(error, "error")
    return render_template("events/party.html", event=event, friends=friends, team=team, joining_now=joining_now,
                           room=room_for(event, team, me), challenge=joining_now and team == 2,
                           host_ok=needs_host_ok(event), max_note=MAX_NOTE)


def send_party(event, chosen, team, joining_now, note=""):
    """Join (if needed) and hold a spot for each chosen friend, all or nothing. Returns an error or None.
    In a private game (unless I'm the host) the friends are only requested: the host says yes first."""
    db = get_db()
    me = g.user["id"]
    ask_host = needs_host_ok(event)
    db.commit()
    db.execute("BEGIN IMMEDIATE")  # nobody else can grab spots between the check and the invites
    try:
        room = room_for(event, team, me)
        needed = (0 if ask_host else len(chosen)) + (1 if joining_now else 0)
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
        expires = to_db(now_local() + HOLD_TIME) if not ask_host else now_param()
        for friend_id in chosen:
            db.execute("""INSERT OR REPLACE INTO invites (event_id, inviter_id, guest_id, team, status, note,
                                                          created_at, expires_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                       (event["id"], me, friend_id, team, "requested" if ask_host else "pending", note,
                        now_param(), expires))
            if not ask_host:
                notify(friend_id, "invites", f"{first} wants you in {title} ({fmt_when(event['starts_at'])}). You down?",
                       url_for("events.detail", event_id=event["id"]))
        if ask_host:
            names = [row["full_name"].split()[0] for row in db.execute(
                f"SELECT full_name FROM users WHERE id IN ({', '.join('?' for _ in chosen)})", chosen)]
            notify(event["host_id"], "invites",
                   f"{first} wants to bring {', '.join(names)} to {title}" + (f": “{note}”" if note else "."),
                   url_for("events.detail", event_id=event["id"]) + "#requests")
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


@bp.route("/events/<int:event_id>/requests/<int:guest_id>/<action>", methods=("POST",))
@login_required
def answer_request(event_id, guest_id, action):
    """The host of a private game says yes (the friend gets the invite and a held spot) or no."""
    if action not in ("approve", "decline"):
        abort(404)
    event = get_event(event_id, host_only=True)
    db = get_db()
    request_row = db.execute("""SELECT i.*, u.full_name AS guest_name FROM invites i JOIN users u ON u.id = i.guest_id
                                WHERE i.event_id = ? AND i.guest_id = ? AND i.status = 'requested'""",
                             (event_id, guest_id)).fetchone()
    if request_row is None:
        abort(404)
    guest_first, host_first, title = request_row["guest_name"].split()[0], g.user["full_name"].split()[0], event_title(event)
    link = url_for("events.detail", event_id=event_id)
    if action == "decline":
        db.execute("UPDATE invites SET status = 'declined' WHERE id = ?", (request_row["id"],))
        notify(request_row["inviter_id"], "invites", f"{host_first} can't fit {guest_first} into {title}.", link)
        db.commit()
        flash("Declined.", "info")
        return redirect(link + "#requests")
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    try:
        room = room_for(event, request_row["team"], None)
        if room is not None and room < 1:
            db.rollback()
            flash("No spots left for them.", "error")
            return redirect(link + "#requests")
        db.execute("UPDATE invites SET status = 'pending', expires_at = ? WHERE id = ?",
                   (to_db(now_local() + HOLD_TIME), request_row["id"]))
        inviter = db.execute("SELECT full_name FROM users WHERE id = ?", (request_row["inviter_id"],)).fetchone()
        notify(guest_id, "invites",
               f"{inviter['full_name'].split()[0]} wants you in {title} ({fmt_when(event['starts_at'])}). You down?", link)
        notify(request_row["inviter_id"], "invites", f"{host_first} said yes to {guest_first} for {title}.", link)
        db.commit()
    except Exception:
        db.rollback()
        raise
    flash(f"Approved. {guest_first}'s spot is held for 30 minutes.", "success")
    return redirect(link + "#requests")


@bp.route("/events/<int:event_id>/invite/<int:guest_id>/cancel", methods=("POST",))
@login_required
def cancel_invite(event_id, guest_id):
    """Take back an invite you sent (frees the held spot)."""
    db = get_db()
    cur = db.execute("""UPDATE invites SET status = 'canceled'
                        WHERE event_id = ? AND guest_id = ? AND inviter_id = ? AND status IN ('pending', 'requested')""",
                     (event_id, guest_id, g.user["id"]))
    db.commit()
    if not cur.rowcount:
        abort(404)
    flash("Invite canceled.", "info")
    return redirect(url_for("events.detail", event_id=event_id))


def can_party_up(event):
    """For templates: show "Party up" on this game?"""
    return g.get("user") is not None and party_plan(event)[2] is None
