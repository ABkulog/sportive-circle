"""Full links to pages on the site, for emails, calendar files and share buttons.

They use PUBLIC_URL (the site's real address) instead of whatever address a request came in on,
so a link in an email always points at the live site, even behind a proxy or load balancer.
"""
from flask import current_app, url_for


def public_url(endpoint, **values):
    """public_url("events.detail", event_id=3) -> "https://sportivecircle.com/events/3"."""
    return current_app.config["PUBLIC_URL"].rstrip("/") + url_for(endpoint, **values)
