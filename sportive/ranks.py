"""Per-sport ranks, like MyCareer in 2K: everyone starts at Casual and works their way up.

Rep comes from playing, hosting and getting props. To move up a tier you also need
vouches from people who actually played with you, so nobody can just walk into
Competitive games without earning it. Everything is positive: no losses, no downvotes.
"""
from collections import namedtuple
from datetime import timedelta

from flask import g

from .constants import SPORTS
from .db import get_db
from .timeutil import from_db, now_local, to_db

# (tier, number, rep needed). Index in this list = the level.
LEVELS = [
    ("Casual", 1, 0), ("Casual", 2, 40), ("Casual", 3, 90),
    ("Intermediate", 1, 150), ("Intermediate", 2, 240), ("Intermediate", 3, 350),
    ("Competitive", 1, 500), ("Competitive", 2, 700), ("Competitive", 3, 950),
    ("Legend", 0, 1300),
]
TIERS = ["Casual", "Intermediate", "Competitive", "Legend"]
FIRST_LEVEL_OF = {tier: next(i for i, level in enumerate(LEVELS) if level[0] == tier) for tier in TIERS}

# Vouches needed to enter a tier. For Competitive, only vouches from players who are
# Intermediate or higher in that sport count.
VOUCHES_NEEDED = {"Intermediate": 3, "Competitive": 5}

# Placement (the fast track for players who are already good): this many vouches from
# players at a tier puts you straight into that tier, no matter how little rep you have.
# One or two games with good players is enough; no grinding through Casual.
PLACEMENT_VOUCHES = 3

REP_PLAY = 10                                            # every game you play
REP_LEVEL_BONUS = {"Intermediate": 5, "Competitive": 10}  # harder games are worth more
REP_HOST = 10                                            # hosting a game that actually happened
REP_PROPS = 5                                            # each 🤝 props you receive
PROPS_WINDOW = timedelta(days=7)                         # how long after a game you can give props

# Which event skill levels need which tier (Casual and All levels are open to everyone).
LEVEL_REQUIREMENT = {"Intermediate": "Intermediate", "Competitive": "Competitive"}

Rank = namedtuple("Rank", "sport level tier name rep next_name next_rep progress blocked_by vouches vouches_needed")


def level_name(level):
    tier, number, _ = LEVELS[level]
    return tier if tier == "Legend" else f"{tier} {number}"


def sport_rep(user_id):
    """{sport: rep} from finished games, hosting and props received."""
    db = get_db()
    rep = {}
    games = db.execute(
        """SELECT e.sport, e.skill_level, e.host_id, e.extra_players,
                  (SELECT COUNT(*) FROM rsvps x WHERE x.event_id = e.id) AS going
           FROM events e JOIN rsvps r ON r.event_id = e.id
           WHERE r.user_id = ? AND e.cancelled = 0 AND e.ends_at < ?""",
        (user_id, to_db(now_local())),
    ).fetchall()
    for game in games:
        points = REP_PLAY + REP_LEVEL_BONUS.get(game["skill_level"], 0)
        if game["host_id"] == user_id and game["going"] + game["extra_players"] >= 2:
            points += REP_HOST
        rep[game["sport"]] = rep.get(game["sport"], 0) + points
    for row in db.execute(
        """SELECT e.sport, COUNT(*) AS n FROM props p JOIN events e ON e.id = p.event_id
           WHERE p.receiver_id = ? GROUP BY e.sport""", (user_id,)):
        rep[row["sport"]] = rep.get(row["sport"], 0) + REP_PROPS * row["n"]
    return rep


def _raw_vouches(user_id, sport):
    return get_db().execute("SELECT COUNT(*) FROM vouches WHERE receiver_id = ? AND sport = ?",
                            (user_id, sport)).fetchone()[0]


def _is_intermediate_or_higher(user_id, sport):
    """Without recursion: enough rep for Intermediate and enough vouches to enter it."""
    return (sport_rep(user_id).get(sport, 0) >= LEVELS[FIRST_LEVEL_OF["Intermediate"]][2]
            and _raw_vouches(user_id, sport) >= VOUCHES_NEEDED["Intermediate"])


def _last_seen_level(user_id, sport):
    row = get_db().execute("SELECT level FROM ranks_seen WHERE user_id = ? AND sport = ?",
                           (user_id, sport)).fetchone()
    return row["level"] if row else 0


def vouch_counts(user_id, sport):
    """(all vouches, from Intermediate-or-higher players, from Competitive-or-higher players).

    A voucher's tier is the rank they last had in the app (saved every time they visit),
    or, for Intermediate, their rep + vouches. This avoids endless "who vouched for whom" loops.
    """
    givers = [row["giver_id"] for row in get_db().execute(
        "SELECT giver_id FROM vouches WHERE receiver_id = ? AND sport = ?", (user_id, sport))]
    strong = elite = 0
    for giver in givers:
        seen = _last_seen_level(giver, sport)
        if seen >= FIRST_LEVEL_OF["Intermediate"] or _is_intermediate_or_higher(giver, sport):
            strong += 1
        if seen >= FIRST_LEVEL_OF["Competitive"]:
            elite += 1
    return len(givers), strong, elite


def compute_rank(sport, rep, vouches_any, vouches_strong, vouches_elite=0):
    level = max(i for i, (_, _, need) in enumerate(LEVELS) if rep >= need)
    blocked_by, have, needed = None, 0, 0
    if level >= FIRST_LEVEL_OF["Intermediate"] and vouches_any < VOUCHES_NEEDED["Intermediate"]:
        level = FIRST_LEVEL_OF["Intermediate"] - 1
        blocked_by, have, needed = "Intermediate", vouches_any, VOUCHES_NEEDED["Intermediate"]
    elif level >= FIRST_LEVEL_OF["Competitive"] and vouches_strong < VOUCHES_NEEDED["Competitive"]:
        level = FIRST_LEVEL_OF["Competitive"] - 1
        blocked_by, have, needed = "Competitive", vouches_strong, VOUCHES_NEEDED["Competitive"]

    # Placement: good players vouched in by good players skip the grind.
    placed = None
    if vouches_elite >= PLACEMENT_VOUCHES and level < FIRST_LEVEL_OF["Competitive"]:
        placed = FIRST_LEVEL_OF["Competitive"]
    elif vouches_strong >= PLACEMENT_VOUCHES and level < FIRST_LEVEL_OF["Intermediate"]:
        placed = FIRST_LEVEL_OF["Intermediate"]
    if placed is not None:
        level = placed
        blocked_by, have, needed = None, 0, 0

    tier = LEVELS[level][0]
    if level + 1 < len(LEVELS):
        next_name, next_rep = level_name(level + 1), LEVELS[level + 1][2]
        start = LEVELS[level][2]
        progress = max(0, min(100, int((rep - start) * 100 / (next_rep - start)))) if not blocked_by else 100
    else:
        next_name, next_rep, progress = None, None, 100
    return Rank(sport, level, tier, level_name(level), rep, next_name, next_rep, progress,
                blocked_by, have, needed)


def user_ranks(user_id):
    """{sport: Rank} for every sport this person has rep or vouches in."""
    rep = sport_rep(user_id)
    vouched = {row["sport"] for row in get_db().execute(
        "SELECT DISTINCT sport FROM vouches WHERE receiver_id = ?", (user_id,))}
    ranks = {}
    for sport in sorted(set(rep) | vouched, key=lambda s: -rep.get(s, 0)):
        if sport in SPORTS:
            ranks[sport] = compute_rank(sport, rep.get(sport, 0), *vouch_counts(user_id, sport))
    return ranks


def my_ranks():
    """The logged-in person's ranks, computed once per request."""
    if "my_ranks" not in g:
        g.my_ranks = user_ranks(g.user["id"]) if g.get("user") is not None else {}
    return g.my_ranks


def tier_index(ranks, sport):
    rank = ranks.get(sport)
    return TIERS.index(rank.tier) if rank else 0


def level_allowed(ranks, sport, skill_level):
    """(allowed, reason) for joining/hosting a game of this skill level."""
    needed = LEVEL_REQUIREMENT.get(skill_level)
    if needed is None:
        return True, None
    if tier_index(ranks, sport) >= TIERS.index(needed):
        return True, None
    current = ranks[sport].name if sport in ranks else "Casual 1"
    return False, (f"For players who've reached {needed} in {SPORTS[sport]}. You're {current}: "
                   f"keep playing and get vouched to rank up! 🐺")


def my_tier_map():
    """For the event forms: {sport: tier index} for the logged-in person (0 = Casual)."""
    ranks = my_ranks()
    return {sport: tier_index(ranks, sport) for sport in SPORTS}


def can_join_level(sport, skill_level):
    """For templates: may the logged-in person join this level of game?"""
    return level_allowed(my_ranks(), sport, skill_level)[0]


def check_rank_ups(user_id, ranks=None):
    """Rank-ups since this person last looked. Returns messages and remembers the new ranks."""
    ranks = ranks if ranks is not None else user_ranks(user_id)
    db = get_db()
    seen = {row["sport"]: row["level"] for row in db.execute(
        "SELECT sport, level FROM ranks_seen WHERE user_id = ?", (user_id,))}
    messages = []
    for sport, rank in ranks.items():
        if rank.level > seen.get(sport, 0):
            messages.append(f"RANK UP! {SPORTS[sport]}: you're now {rank.name} 🔥")
        if rank.level != seen.get(sport):
            db.execute("INSERT OR REPLACE INTO ranks_seen (user_id, sport, level) VALUES (?, ?, ?)",
                       (user_id, sport, rank.level))
    db.commit()
    return messages


# ------------------------------------------------------------- props & vouches

def played_together(event_id, user_a, user_b):
    return get_db().execute(
        "SELECT COUNT(*) FROM rsvps WHERE event_id = ? AND user_id IN (?, ?)", (event_id, user_a, user_b)
    ).fetchone()[0] == 2


def props_open(event):
    """Props can be given from the end of a game until a week later."""
    ends = from_db(event["ends_at"])
    return not event["cancelled"] and ends < now_local() <= ends + PROPS_WINDOW
