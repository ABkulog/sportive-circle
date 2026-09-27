"""Per-sport numbers for tuning SPORT_MAX_PLAYERS in constants.py once real people use the app.

    .venv/bin/flask --app main sport-stats
"""
import click
from flask.cli import with_appcontext

from .constants import SPORT_MAX_PLAYERS, SPORTS
from .db import get_db
from .timeutil import now_local, to_db


def sport_stats():
    """For each sport: how many events, the player limit hosts choose, and how many actually joined.

    Only finished, non-cancelled events count, so the numbers reflect real games.
    """
    rows = get_db().execute(
        """SELECT e.sport,
                  COUNT(*) AS events,
                  AVG(e.max_players) AS avg_limit,
                  MAX(e.max_players) AS biggest_limit,
                  AVG(e.extra_players + (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id)) AS avg_players,
                  MAX(e.extra_players + (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id)) AS most_players,
                  AVG(CASE WHEN e.max_players IS NOT NULL AND
                           e.extra_players + (SELECT COUNT(*) FROM rsvps r WHERE r.event_id = e.id) >= e.max_players
                      THEN 1.0 ELSE 0.0 END) AS share_full
           FROM events e
           WHERE e.cancelled = 0 AND e.ends_at < ?
           GROUP BY e.sport
           ORDER BY events DESC""",
        (to_db(now_local()),),
    ).fetchall()
    return [dict(row) for row in rows]


@click.command("sport-stats")
@with_appcontext
def sport_stats_command():
    rows = sport_stats()
    if not rows:
        click.echo("No finished events yet. Check back once people have played some games.")
        return
    click.echo(f"{'Sport':<22}{'Events':>7}{'Cap':>6}{'Avg limit':>11}{'Avg players':>13}{'Most':>6}{'Full':>7}")
    for row in rows:
        avg_limit = f"{row['avg_limit']:.1f}" if row["avg_limit"] is not None else "-"
        click.echo(
            f"{SPORTS.get(row['sport'], row['sport']):<22}{row['events']:>7}{SPORT_MAX_PLAYERS.get(row['sport'], 0):>6}"
            f"{avg_limit:>11}{row['avg_players']:>13.1f}{row['most_players']:>6}{row['share_full']:>7.0%}"
        )
    click.echo("\nIf games in a sport often fill up, its cap may be too low; if 'Most' never gets")
    click.echo("near the cap, you can lower it. Change the caps in sportive/constants.py.")
