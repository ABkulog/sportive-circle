"""Simple pages: How it works, FAQ, Privacy, Terms, the Create menu, and icons browsers ask for."""
import io

from flask import Response, current_app, g, redirect, render_template, request, url_for

from .auth import login_required
from .clubs import officer_clubs
from .db import get_db


def how_it_works():
    return render_template("pages/how_it_works.html")


def faq():
    return render_template("pages/faq.html")


def privacy():
    return render_template("pages/privacy.html")


def terms():
    return render_template("pages/terms.html")


@login_required
def create_menu():
    return render_template("pages/create.html", officer_clubs=officer_clubs(g.user["id"]))


def favicon():
    """Browsers ask for /favicon.ico on their own; point them at the real icon."""
    return redirect(url_for("static", filename="icon.svg"))


def touch_icon():
    """iPhones ask for this when someone adds the site to their home screen."""
    return redirect(url_for("static", filename="apple-touch-icon.png"))


# Pages that are for logged-in people (or private) stay out of search engines.
PRIVATE_PATHS = ("/messages", "/profile", "/admin", "/notifications", "/friends", "/me/", "/u/", "/verify",
                 "/reset", "/tasks/", "/suggestions", "/settings")


def robots():
    site = current_app.config["PUBLIC_URL"].rstrip("/")
    lines = ["User-agent: *", *(f"Disallow: {path}" for path in PRIVATE_PATHS), f"Sitemap: {site}/sitemap.xml"]
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


def sitemap():
    """The public pages, so Google can list Sportive Circle (and every verified club) in search results."""
    site = current_app.config["PUBLIC_URL"].rstrip("/")
    paths = [url_for(name) for name in ("index", "how_it_works", "faq", "privacy", "terms", "auth.signup")]
    paths.append(url_for("clubs.directory"))
    paths += [url_for("clubs.view", club_id=row["id"]) for row in get_db().execute(
        "SELECT id FROM clubs WHERE status = 'approved' ORDER BY id")]
    urls = "".join(f"<url><loc>{site}{path}</loc></url>" for path in paths)
    return Response('<?xml version="1.0" encoding="UTF-8"?>'
                    f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                    mimetype="application/xml")


VERBS = {"running": "Run", "hiking": "Hike", "biking": "Ride", "climbing": "Climb", "rowing": "Row"}


def _flyer_target():
    """(club or None, the link the QR opens): ?club=<id> for a verified club's flyer, else the site."""
    from .links import public_url
    club_id = request.args.get("club", type=int)
    club = get_db().execute("SELECT id, name, sport FROM clubs WHERE id = ? AND status = 'approved'",
                            (club_id,)).fetchone() if club_id else None
    return club, public_url("clubs.view", club_id=club["id"]) if club else public_url("index")


def flyer():
    """A one-page printable flyer: headline, three steps and a big QR code (for a club, or the whole app)."""
    club, link = _flyer_target()
    headline = f"{VERBS.get(club['sport'], 'Play')} with {club['name']}" if club else "Find people to play with"
    return render_template("pages/flyer.html", club=club, link=link, headline=headline,
                           qr=url_for("flyer_qr", club=club["id"] if club else None))


def flyer_qr():
    import segno  # only needed here
    code = segno.make(_flyer_target()[1], error="m")
    output = io.BytesIO()
    code.save(output, kind="svg", scale=10, dark="#4b2e83", light="#ffffff", border=2, xmldecl=False)
    response = Response(output.getvalue(), mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


def register(app):
    app.add_url_rule("/flyer", "flyer", flyer)
    app.add_url_rule("/flyer/qr.svg", "flyer_qr", flyer_qr)
    app.add_url_rule("/how-it-works", "how_it_works", how_it_works)
    app.add_url_rule("/faq", "faq", faq)
    app.add_url_rule("/privacy", "privacy", privacy)
    app.add_url_rule("/terms", "terms", terms)
    app.add_url_rule("/create", "create_menu", create_menu)
    app.add_url_rule("/favicon.ico", "favicon", favicon)
    app.add_url_rule("/robots.txt", "robots", robots)
    app.add_url_rule("/sitemap.xml", "sitemap", sitemap)
    app.add_url_rule("/apple-touch-icon.png", "touch_icon", touch_icon)
    app.add_url_rule("/apple-touch-icon-precomposed.png", "touch_icon_precomposed", touch_icon)
