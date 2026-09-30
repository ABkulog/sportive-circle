"""Parties: play with your friends.

"Reserve spots" on a game (the host can also do it while creating one): pick friends, and each gets a
notice ("You down?") while their spot is held for 30 minutes. If you're not in the game yet, you join at the same time, so a whole group gets in at once.
Yes takes the held spot; No frees it for someone else.

Team vs team: the host's party is team 1. Another group "challenges" them by claiming team 2 the same
way (the leader joins and holds spots for their friends).
"""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, URLSafeSerializer

from .auth import login_required
from .db import get_db
from .events import KEPT_OUT, event_title, get_event, kept_out, not_for_me, query_events, spots_left, try_join
from .links import public_url
from .invites import HOLD_TIME, MAX_PARTY, held_spots, hold_spots, my_invite, now_param, team_counts
from .sms import drop_queued_texts, queue_text
from .notifications import notify
from .social import can_message, friends_of, is_blocked_between, too_many_messages
from .textutil import one_line
from .timeutil import fmt_when, from_db, now_local, to_db

bp = Blueprint("parties", __name__)

MAX_NOTE = 150  # "this is my roommate": the note for the host of a private game


def invitable_friends(event_id, me):
    """My friends who aren't in this game and haven't been invited to it yet (blocked people aren't friends)."""
    return get_db().execute(
        """SELECT u.id, u.full_name, u.avatar_updated FROM friendships f
           JOIN users u ON u.id = CASE WHEN f.requester_id = :me THEN f.addressee_id ELSE f.requester_id END
           WHERE (f.requester_id = :me OR f.addressee_id = :me) AND f.status = 'accepted'
             AND u.suspended = 0
             AND NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.blocker_id = :me AND b.blocked_id = u.id)
                                                      OR (b.blocker_id = u.id AND b.blocked_id = :me))
             AND u.id NOT IN (SELECT user_id FROM rsvps WHERE event_id = :event)
             AND u.id NOT IN (SELECT guest_id FROM invites WHERE event_id = :event AND status IN ('pending', 'requested'))
           ORDER BY u.full_name""", {"me": me, "event": event_id}).fetchall()


def party_plan(event):
    """What "Party up" means for me in this game: (team, joining_now, problem).

    team is None for regular games; joining_now = I'm not in yet and join together with my party.
    A full game (or team) says so, instead of showing a page with "0 spots" and no reason.
    """
    team, joining_now, problem = _party_plan(event)
    if problem is None:
        room = room_for(event, team, g.user["id"])
        if room is not None and room - (1 if joining_now else 0) <= 0:
            what = "Your team is" if team is not None and not joining_now else "This game is"
            return team, joining_now, (f"{what} full, so there's no spot to reserve for a friend. "
                                       "If someone leaves, you can reserve it then.")
    return team, joining_now, problem


def _party_plan(event):
    me = g.user["id"]
    if event["cancelled"] or from_db(event["ends_at"]) < now_local():
        return None, False, "This game is over."
    if is_blocked_between(me, event["host_id"]):
        return None, False, "You can't join this game."
    mine = get_db().execute("SELECT team FROM rsvps WHERE event_id = ? AND user_id = ?",
                            (event["id"], me)).fetchone()
    invite = None if mine else my_invite(event["id"], me)
    if not mine:  # joining now: the same rules as the Join button
        if not_for_me(event):
            return None, False, not_for_me(event)
        if kept_out(event, invite):
            return None, False, KEPT_OUT
        if event["members_only"] and not event["i_am_member"]:
            return None, False, f"This event is for {event['club_name']} members."
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
                    flash("Invites sent." if event["is_private"] else
                          f"Reserved! Their spot{'s are' if len(chosen) > 1 else ' is'} held for 30 minutes.",
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
            drop_queued_texts()
            for_friends = room - (1 if joining_now else 0)
            if for_friends <= 0:
                return "Sorry, there's no room for a party in this game."
            return f"Only {for_friends} spot{'s' if for_friends != 1 else ''} left for friends."
        title, first = event_title(event), g.user["full_name"].split()[0]
        if joining_now:
            db.execute("INSERT OR IGNORE INTO rsvps (event_id, user_id, created_at, team) VALUES (?, ?, ?, ?)",
                       (event["id"], me, now_param(), team))
            mine = my_invite(event["id"], me)
            if mine:  # I was invited myself: that invite is answered now
                db.execute("UPDATE invites SET status = 'accepted' WHERE id = ?", (mine["id"],))
                notify(mine["inviter_id"], "invites", f"{first} is in for {title}.",
                       url_for("events.detail", event_id=event["id"]), key=f"reply:{event['id']}:{me}")
        link = url_for("events.detail", event_id=event["id"])
        if not ask_host:
            hold_spots(event["id"], me, chosen, team,
                       f"{first} wants you in {title} ({fmt_when(event['starts_at'])}). You down?", link)
        else:
            for friend_id in chosen:  # requests: nothing is held until the host says yes
                db.execute("""INSERT OR REPLACE INTO invites (event_id, inviter_id, guest_id, team, status, note,
                                                              created_at, expires_at)
                              VALUES (?, ?, ?, ?, 'requested', ?, ?, ?)""",
                           (event["id"], me, friend_id, team, note, now_param(), now_param()))
            names = [row["full_name"].split()[0] for row in db.execute(
                f"SELECT full_name FROM users WHERE id IN ({', '.join('?' for _ in chosen)})", chosen)]
            notify(event["host_id"], "invites",
                   f"{first} wants to bring {', '.join(names)} to {title}" + (f": “{note}”" if note else "."),
                   url_for("events.detail", event_id=event["id"]) + "#requests", key=f"request:{event['id']}:{me}")
        db.commit()
    except Exception:
        db.rollback()
        drop_queued_texts()
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
               url_for("events.detail", event_id=event_id), key=f"reply:{event_id}:{g.user['id']}")
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
        notify(request_row["inviter_id"], "invites", f"{host_first} can't fit {guest_first} into {title}.", link,
               key=f"reply:{event_id}:{guest_id}")
        db.commit()
        flash("Declined.", "info")
        return redirect(link + "#requests")
    db.commit()
    db.execute("BEGIN IMMEDIATE")
    try:
        room = room_for(event, request_row["team"], None)
        if room is not None and room < 1:
            db.rollback()
            drop_queued_texts()
            flash("No spots left for them.", "error")
            return redirect(link + "#requests")
        db.execute("UPDATE invites SET status = 'pending', expires_at = ? WHERE id = ?",
                   (to_db(now_local() + HOLD_TIME), request_row["id"]))
        inviter = db.execute("SELECT full_name FROM users WHERE id = ?", (request_row["inviter_id"],)).fetchone()
        message = f"{inviter['full_name'].split()[0]} wants you in {title} ({fmt_when(event['starts_at'])}). You down?"
        notify(guest_id, "invites", message, link, key=f"invite:{event_id}")
        queue_text(guest_id, f"{message} Your spot is held for 30 min: "
                             f"{current_app.config['PUBLIC_URL'].rstrip('/')}{link}")  # sent after the save
        notify(request_row["inviter_id"], "invites", f"{host_first} said yes to {guest_first} for {title}.", link,
               key=f"reply:{event_id}:{guest_id}")
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


# ---------------------------------------------------------------- invite links (for friends not on the app)
# "Jordan wants you in their Sportive Circle game. Tap to sign up and you're in." The link is signed with the
# app's secret key, so nobody can make one for a game they aren't in, or pretend to be someone else.
# Game 0 = just "join me on Sportive Circle" (you become friends).

def _signer():
    return URLSafeSerializer(current_app.secret_key, salt="invite-link")


def invite_link(event_id=0):
    """The logged-in person's invite link for a game (or for the app, with event_id 0)."""
    return public_url("parties.open_invite_link", token=_signer().dumps([int(event_id), g.user["id"]]))


def _read_link(token):
    try:
        event_id, inviter_id = _signer().loads(token)
        return int(event_id), int(inviter_id)
    except (BadSignature, ValueError, TypeError):
        return None


def _open_game(event_id):
    rows = query_events(["e.id = :id", "e.cancelled = 0", "e.ends_at >= :now"],
                        {"id": event_id, "now": now_param()}, limit=1) if event_id else []
    return rows[0] if rows else None


@bp.route("/join/<token>", methods=("GET", "POST"))
def open_invite_link(token):
    """Opening the link only shows what it's for. Joining takes a tap (a POST), so a link hidden in an image or
    opened by a link preview can't put anyone in a game or make them friends."""
    link = _read_link(token)
    inviter = get_db().execute("SELECT id, full_name FROM users WHERE id = ? AND verified = 1 AND suspended = 0",
                               (link[1],)).fetchone() if link else None
    if inviter is None:
        flash("That invite link doesn't work anymore.", "error")
        return redirect(url_for("index"))
    if g.get("user") is not None and request.method == "POST":
        return redirect(accept_invite_link(g.user, token) or url_for("index"))
    if request.method == "POST":  # logged out and tapped "Sign up and join" / "I have an account"
        session["invite_link"] = token  # used right after they sign up or log in (auth.log_in)
        return redirect(url_for("auth.login" if request.form.get("go") == "login" else "auth.signup"))
    event = _open_game(link[0]) if link[0] else None
    if g.get("user") is not None and inviter["id"] == g.user["id"]:
        return redirect(url_for("events.detail", event_id=event["id"]) if event else url_for("social.friends"))
    full = bool(event) and spots_left(event) == 0 and not event["i_am_going"]
    return render_template("events/invite_link.html", inviter=inviter, event=event, token=token, full=full)


def accept_invite_link(user, token):
    """Someone opened a friend's invite link and is now logged in (maybe just signed up): make them friends and,
    if it was for a game, put them in it. Returns where to go next (None = nowhere special)."""
    link = _read_link(token)
    if link is None or link[1] == user["id"]:
        return None
    event_id, inviter_id = link
    db = get_db()
    if is_blocked_between(user["id"], inviter_id):
        return None
    g.user = user  # they may have logged in during this very request
    first = user["full_name"].split()[0]
    friends = db.execute("""SELECT 1 FROM friendships WHERE (requester_id = ? AND addressee_id = ?)
                            OR (requester_id = ? AND addressee_id = ?)""",
                         (inviter_id, user["id"], user["id"], inviter_id)).fetchone()
    if friends:
        db.execute("""UPDATE friendships SET status = 'accepted' WHERE (requester_id = ? AND addressee_id = ?)
                      OR (requester_id = ? AND addressee_id = ?)""", (inviter_id, user["id"], user["id"], inviter_id))
    else:
        db.execute("INSERT OR IGNORE INTO friendships (requester_id, addressee_id, status, created_at) VALUES (?, ?, 'accepted', ?)",
                   (inviter_id, user["id"], now_param()))
    db.commit()
    event = _open_game(event_id)
    if event is None:
        if event_id:
            flash("That game is over or was canceled, but you and your friend are connected now.", "info")
        return url_for("social.friends") if not event_id else url_for("events.feed")
    if event["i_am_going"]:
        return url_for("events.detail", event_id=event_id)
    inviter_team = db.execute("SELECT team FROM rsvps WHERE event_id = ? AND user_id = ?",
                              (event_id, inviter_id)).fetchone()
    if inviter_team is None:  # the friend left the game since sending the link
        flash("Your friend isn't in that game anymore.", "info")
        return url_for("events.detail", event_id=event_id)
    if event["is_private"] and inviter_id != event["host_id"]:
        # Same rule as "Invite friends" in a private game: the host says yes before a player's friend gets in.
        db.execute("""INSERT OR REPLACE INTO invites (event_id, inviter_id, guest_id, team, status, note, created_at,
                                                      expires_at) VALUES (?, ?, ?, ?, 'requested', '', ?, ?)""",
                   (event_id, inviter_id, user["id"], inviter_team["team"], now_param(), now_param()))
        inviter = db.execute("SELECT full_name FROM users WHERE id = ?", (inviter_id,)).fetchone()
        notify(event["host_id"], "invites",
               f"{inviter['full_name'].split()[0]} wants to bring {first} to {event_title(event)}.",
               url_for("events.detail", event_id=event_id) + "#requests", key=f"request:{event_id}:{inviter_id}")
        db.commit()
        flash(f"Asked {event['host_name'].split()[0]}, the host. You'll get the invite once they say yes.", "info")
        return url_for("events.detail", event_id=event_id)
    # The link counts as an invite (so a private game's password isn't needed), then join like anyone else.
    db.execute("""INSERT OR REPLACE INTO invites (event_id, inviter_id, guest_id, team, status, created_at, expires_at)
                  VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
               (event_id, inviter_id, user["id"], inviter_team["team"], now_param(), now_param()))
    db.commit()
    joined, message = try_join(get_event(event_id), None)
    flash(f"You're in {event_title(event)}!" if joined else message, "celebrate" if joined else "error")
    if joined:
        notify(inviter_id, "invites", f"{first} joined from your link and is in {event_title(event)}.",
               url_for("events.detail", event_id=event_id), key=f"reply:{event_id}:{user['id']}")
        db.commit()
    return url_for("events.detail", event_id=event_id)


# ---------------------------------------------------------------- send a game to friends

MAX_SHARE_NOTE = 300


def can_send_to_friends(event):
    """'Send to friends' is for public games that haven't ended (private games use the invite link / password)."""
    return (not event["is_private"] and not event["cancelled"]
            and from_db(event["ends_at"]) >= now_local())


def sharable_friends(event_id, me):
    """My friends who aren't already going (blocked people aren't friends)."""
    going = {row[0] for row in get_db().execute("SELECT user_id FROM rsvps WHERE event_id = ?", (event_id,))}
    return [friend for friend in friends_of(me) if friend["id"] not in going]


@bp.route("/events/<int:event_id>/send", methods=("GET", "POST"))
@login_required
def send_to_friends(event_id):
    """Share a public game with friends on the app: each one gets it as a direct message with a game card."""
    event = get_event(event_id)
    me = g.user["id"]
    if not can_send_to_friends(event):
        flash("Only open games that haven't ended can be sent to friends.", "error")
        return redirect(url_for("events.detail", event_id=event_id))
    friends = sharable_friends(event_id, me)
    if request.method == "POST":
        allowed = {friend["id"] for friend in friends}
        chosen = list(dict.fromkeys(int(value) for value in request.form.getlist("friend") if value.isdigit()))
        note = one_line(request.form.get("note"))[:MAX_SHARE_NOTE]
        if not chosen:
            flash("Pick at least one friend.", "error")
        elif any(friend_id not in allowed or not can_message(me, friend_id) for friend_id in chosen):
            flash("You can only send games to your friends.", "error")
        elif len(chosen) > MAX_PARTY:
            flash(f"You can send it to up to {MAX_PARTY} friends at once.", "error")
        elif too_many_messages(me):
            flash("Whoa, slow down! Wait a minute before sending more messages.", "error")
        else:
            body = note or f"Want to play? {event_title(event)}, {fmt_when(event['starts_at'])}."
            now = to_db(now_local())
            db = get_db()
            db.executemany("INSERT INTO direct_messages (sender_id, recipient_id, body, created_at, event_id)"
                           " VALUES (?, ?, ?, ?, ?)", [(me, friend_id, body, now, event_id) for friend_id in chosen])
            db.commit()
            names = [friend["full_name"].split()[0] for friend in friends if friend["id"] in chosen]
            flash(f"Sent to {names[0]}." if len(names) == 1 else f"Sent to {len(names)} friends.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
    return render_template("events/send.html", event=event, friends=friends, max_note=MAX_SHARE_NOTE)
