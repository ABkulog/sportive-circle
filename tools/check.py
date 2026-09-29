"""The full check: run after EVERY change, before committing.

    .venv/bin/python tools/check.py

1. Code check (pyflakes): unused or misspelled names.
2. All tests: unit tests and the Gherkin scenarios.
3. Link crawl: every page reachable by links, as a visitor, a student and an admin (0 broken allowed).
   Every page is also checked for: a <title>, exactly one <h1>, no duplicate ids, no template leftovers
   ("{{", "Undefined"), and the security headers.
4. Junk-input test: 1,000+ bad requests to every form and URL (0 crashes allowed).
5. With --external: every link to another website still works (needs the internet).

Steps 3 and 4 use a throwaway database filled by seed.py, so real data is never touched.
(The phone/tablet/laptop layout scan runs in a browser; see docs/deployment.md.)
"""
import contextlib
import io
import logging
import os
import re
import subprocess
import sys
import tempfile
from collections import deque
from urllib.parse import urljoin, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
PY = sys.executable


def run(title, args):
    print(f"\n== {title}")
    result = subprocess.run(args, capture_output=True, text=True)
    lines = (result.stdout + result.stderr).strip().splitlines()
    print("\n".join(lines[-3:]) if lines else "OK")
    return result.returncode == 0


def fresh_app():
    import seed
    from sportive import create_app
    folder = tempfile.mkdtemp()
    app = create_app({"TESTING": True, "DATABASE": os.path.join(folder, "check.db"), "SECRET_KEY": "check",
                      "CSRF_ENABLED": False, "ADMIN_EMAILS": "demo.jordan@uw.edu",
                      "PASSWORD_HASH_METHOD": "pbkdf2:sha256:1000", "PROPAGATE_EXCEPTIONS": False})
    seed.create_app = lambda *a, **k: app
    with contextlib.redirect_stdout(io.StringIO()):
        seed.main()
    return app, seed.DEMO_PASSWORD


def logged_in(app, password, email=None):
    client = app.test_client()
    if email:
        client.post("/login", data={"email": email, "password": password})
    return client


# ------------------------------------------------------------------ 3. link crawl

START = ["/", "/how-it-works", "/faq", "/privacy", "/terms", "/clubs", "/create", "/me/events", "/friends",
         "/friends?q=ma", "/messages", "/profile/edit", "/profile/badges", "/profile/notifications", "/settings/notifications", "/settings", "/settings/password", "/settings/texts", "/notifications",
         "/profile/photo",
         "/clubs/updates", "/admin/reports", "/admin/clubs", "/u/1", "/u/2", "/events/new", "/need-players", "/events/1/party", "/events/2/party", "/clubs/1/share", "/clubs/1/qr.svg",
         "/clubs/new", "/signup", "/login", "/forgot", "/suggestions", "/admin/suggestions",
         "/admin/suggestions?kind=bug"]
SKIP = ("/logout", "/static/", "/u/", "photo")


def page_problems(url, response):
    """Small things that are easy to miss on any one page."""
    page = response.get_data(as_text=True)
    problems = []
    if "Content-Security-Policy" not in response.headers:
        problems.append("no security headers")
    if not re.search(r"<title>[^<]+</title>", page):
        problems.append("no <title>")
    if len(re.findall(r"<h1[ >]", page)) != 1:
        problems.append(f"{len(re.findall(r'<h1[ >]', page))} <h1> headings (should be 1)")
    ids = re.findall(r'\sid="([^"]+)"', page)
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate ids {duplicates}")
    visible = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", page, flags=re.S)
    for leftover in ("{{", "{%", "Undefined", "Traceback"):
        if leftover in visible:
            problems.append(f"template leftover {leftover!r}")
    return [f"{url}: {problem}" for problem in problems]


def crawl(app, password, who, email, external):
    client = logged_in(app, password, email)
    seen, bad, queue = set(), [], deque(START)
    while queue:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        response = client.get(url)
        admin_only = url.startswith("/admin") and response.status_code == 404 and who != "admin"
        if response.status_code >= 400 and not admin_only:
            bad.append((response.status_code, url))
        if response.status_code in (301, 302) or "text/html" not in response.content_type:
            continue
        if response.status_code < 400:
            bad.extend(page_problems(url, response))
        for href in re.findall(r'(?:href|src)="([^"#]+)', response.get_data(as_text=True)):
            parsed = urlparse(href)
            if parsed.scheme in ("http", "https"):
                external.add(href.replace("&amp;", "&"))
                continue
            if href.startswith(("mailto:", "tel:", "data:")):
                continue
            path = urlparse(urljoin(url, href))
            path = path.path + ("?" + path.query if path.query else "")
            wanted = not any(s in path for s in SKIP) or (path.startswith("/u/") and path.count("/") == 2)
            if path not in seen and wanted and len(seen) < 700:
                queue.append(path)
    return len(seen), bad


# ------------------------------------------------------------------ 4. junk input

JUNK = ["", " ", "abc", "-1", "0", "99999999999999999999", "1.5", "x" * 100_000, "😀🏀", "<script>alert(1)</script>",
        "a\r\nb", "\x00", "O'Brien", "%", "2026-02-30T25:61", "null", "[]"]

FIELDS = {
    "/signup": ["full_name", "email", "password", "password2", "grad_year", "birth_date", "sports"],
    "/login": ["email", "password", "next"],
    "/forgot": ["email"],
    "/events/new": ["title", "sport", "location", "skill_level", "starts_at", "ends_at", "players", "note",
                    "club", "is_private", "password", "team_size", "reserve", "repeat", "open_to"],
    "/clubs/1/logo/edit": ["logo", "remove"],
    "/events/2/join": ["password", "next"],
    "/events/2/party": ["friend"],
    "/events/2/invite/answer": ["answer"],
    "/events/2/invite/3/cancel": [],
    "/events/1/requests/3/approve": [],
    "/events/1/requests/3/decline": [],
    "/need-players": ["sport", "location", "skill_level", "starts_in", "duration", "players", "note",
                      "is_private", "password", "team_size", "reserve"],
    "/events/2/edit": ["title", "sport", "location", "skill_level", "starts_at", "ends_at", "players", "note"],
    "/profile/edit": ["full_name", "grad_year", "bio", "pronouns", "gender"],
    "/profile/edit/sports": ["sports", "instagram", "snapchat", "tiktok", "x_handle", "linkedin"],
    "/signup/sports": ["sports", "theme"],
    "/signup/texts": ["phone", "consent"],
    "/settings/texts": ["action", "phone", "consent", "code", "sms_updates"],
    "/admin/users/3/tester/give": [],
    "/profile/password": ["current_password", "password", "password2"],
    "/profile/badges": ["show"],
    "/profile/delete": ["confirm", "password"],
    "/clubs/new": ["name", "sport", "description", "verification_url", "contact_phone", "contact_phone_country", "member_estimate", "club_email", "instagram",
                   "facebook", "contact_url", "joining", "focus"],
    "/clubs/1/join": ["message"],
    "/clubs/updates": ["club", "body"],
    "/clubs/1/posts": ["body"],
    "/messages/2": ["body"],
    "/events/2/chat": ["body"],
    "/report/user/2": ["reason", "details", "block"],
    "/admin/clubs/1/reject": ["note"],
    "/profile/photo/remove": [],
    "/suggestions": ["kind", "body", "anonymous"],
    "/settings/notifications": ["messages", "invites", "badges", "club_updates", "bogus_kind"],
    "/settings/look": ["theme"],
    "/settings/reminders": ["email_reminders"],
    "/admin/users/3/suspend": [],
}

GETS = ["/?sport={}", "/?when={}", "/?location={}", "/?skill={}&scope={}", "/?open={}", "/clubs?q={}&sport={}&easy={}",
        "/friends?q={}", "/friends?q={}@uw.edu", "/messages/2/poll?after={}", "/events/2/chat/poll?after={}",
        "/login?next={}", "/signup?next={}", "/clubs/new?sport={}", "/events/new?sport={}&club={}"]

ODD_URLS = ["/events/999999", "/events/0/join", "/clubs/999999", "/u/999999", "/u/999999/photo", "/messages/999999",
            "/report/nothing/1", "/report/dm/999999", "/admin/users/999999/suspend", "/clubs/1/members/999999/approve",
            "/friends/request/999999",
            "/block/999999", "/reset", "/verify", "/profile/notifications",
            "/admin/users/1/explode", "/admin/users/1/tester/explode", "/clubs/999999/share", "/clubs/999999/qr.svg", "/clubs/999999/roster.csv",
            "/clubs/999999/logo", "/join/nonsense", "/join/WzEsIDJd.bad", "/clubs/1/logo/edit", "/clubs/1/roster.csv", "/events/new?club=1", "/events/1/requests/3/explode", "/admin/users/999999/tester/give", "/admin/users/99999999999999999999/suspend"]


def junk_test(app, password):
    crashes = []

    def check(client, method, url, data=None):
        response = client.post(url, data=data) if method == "POST" else client.get(url)
        if response.status_code >= 500:
            crashes.append(f"{method} {url[:80]} {str(data)[:80] if data else ''}")

    for url, names in FIELDS.items():
        for junk in JUNK:
            anonymous = url in ("/signup", "/login", "/forgot")
            client = app.test_client() if anonymous else logged_in(app, password, "demo.jordan@uw.edu")
            check(client, "POST", url, {name: junk for name in names})
            for name in names:
                check(client, "POST", url, {name: junk})
    admin = logged_in(app, password, "demo.jordan@uw.edu")
    for url in GETS:
        for junk in JUNK[:12]:
            check(admin, "GET", url.replace("{}", junk.replace("&", "%26").replace("#", "%23")))
    for url in ODD_URLS:
        check(admin, "GET", url)
        check(admin, "POST", url, {})
        check(app.test_client(), "GET", url)
    return crashes


def check_external(links):
    """Links to other websites that don't answer. Map tiles/CDN files and demo placeholders are skipped."""
    from concurrent.futures import ThreadPoolExecutor
    from urllib.request import Request, urlopen

    def dead(link):
        if any(skip in link for skip in ("example.com", "{z}", "tile.openstreetmap.org", "google.com/maps/dir",
                                         "maps.apple.com", "fonts.g", "cdnjs.cloudflare.com")):
            return None
        for method in ("HEAD", "GET"):
            try:
                request = Request(link, method=method, headers={"User-Agent": "Mozilla/5.0 (SportiveCircle link check)"})
                with urlopen(request, timeout=15) as response:
                    if response.status < 400:
                        return None
            except Exception as error:  # some sites refuse HEAD; GET is the real test
                reason = str(error)
        return f"{link}  ({reason})"

    with ThreadPoolExecutor(max_workers=12) as pool:
        return sorted(filter(None, pool.map(dead, sorted(links))))


def main():
    ok = run("1. Code check (pyflakes)", [PY, "-m", "pyflakes", "sportive", "tests", "tools", "seed.py", "main.py", "wsgi.py"])
    ok &= run("2. Tests (unit + Gherkin)", [PY, "-m", "pytest", "-q"])
    logging.disable(logging.CRITICAL)
    app, password = fresh_app()
    print("\n== 3. Link crawl + page checks")
    external = set()
    for who, email in [("visitor", None), ("student", "demo.maya@uw.edu"), ("admin", "demo.jordan@uw.edu")]:
        pages, bad = crawl(app, password, who, email, external)
        print(f"{who:>8}: {pages} pages, {len(bad)} problems")
        for problem in bad[:15]:
            print("   ", problem)
        ok &= not bad
    print("\n== 4. Junk-input test")
    app, password = fresh_app()
    crashes = junk_test(app, password)
    print(f"{len(crashes)} crashes")
    for crash in crashes[:20]:
        print("  ", crash)
    ok &= not crashes
    if "--external" in sys.argv:
        print(f"\n== 5. External links ({len(external)})")
        dead = check_external(external)
        for link in dead:
            print("   ", link)
        print(f"{len(dead)} dead")
        ok &= not dead
    print("\nALL CHECKS PASSED" if ok else "\nSOMETHING FAILED (see above)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
