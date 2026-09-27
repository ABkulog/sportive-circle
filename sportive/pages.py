"""Simple pages: How it works, Privacy, Terms, the Create menu, and icons browsers ask for."""
from flask import g, redirect, render_template, url_for

from .auth import login_required
from .clubs import officer_clubs


def how_it_works():
    return render_template("pages/how_it_works.html")


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


def register(app):
    app.add_url_rule("/how-it-works", "how_it_works", how_it_works)
    app.add_url_rule("/privacy", "privacy", privacy)
    app.add_url_rule("/terms", "terms", terms)
    app.add_url_rule("/create", "create_menu", create_menu)
    app.add_url_rule("/favicon.ico", "favicon", favicon)
    app.add_url_rule("/apple-touch-icon.png", "touch_icon", touch_icon)
    app.add_url_rule("/apple-touch-icon-precomposed.png", "touch_icon_precomposed", touch_icon)
