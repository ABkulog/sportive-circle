"""Visual audit: the real app on http://127.0.0.1:5070 with a fresh demo database, ready for tools/visual_audit.js.

    .venv/bin/python tools/audit_server.py

Then open http://127.0.0.1:5070 in a browser (log in as demo.jordan@uw.edu, password in seed.py, to also check
admin pages), open the console and run:

    await import("/__audit.js").catch(() => {}); // or: paste tools/visual_audit.js
    const report = await scAudit({start: ["/"], themes: [null, "dark"]});   // crawls, then checks 7 screen sizes
    report.issues

It flags sideways scrolling, things sticking out or overlapping, cut-off text, small tap targets, broken
images, low contrast (light and dark), repeated links, emoji-heavy or wordy screens and phone screens that
need scrolling. Run it logged out AND logged in: some problems only show for visitors.
The only difference from the real site: pages may be shown in a frame on the same address (the audit needs it).
"""
import contextlib
import io
import os
import socket
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import seed  # noqa: E402
from flask import send_file  # noqa: E402
from sportive import CONTENT_SECURITY_POLICY, create_app  # noqa: E402

PORT = int(os.environ.get("AUDIT_PORT", "5070"))
# Check the port first: if another audit server is already running, starting a second one mustn't wipe its database.
with socket.socket() as probe:
    if probe.connect_ex(("127.0.0.1", PORT)) == 0:
        sys.exit(f"Port {PORT} is already in use (another audit server?). Set AUDIT_PORT to use another port.")
DB = os.path.join(tempfile.gettempdir(), f"sportive-audit-{PORT}.db")  # each port its own database
if os.path.exists(DB):
    os.remove(DB)
app = create_app({"DEBUG": True, "DATABASE": DB, "ADMIN_EMAILS": "demo.jordan@uw.edu"})
seed.create_app = lambda *args, **kwargs: app
with contextlib.redirect_stdout(io.StringIO()):
    seed.main()

app.add_url_rule("/__audit.js", "audit_js", lambda: send_file(os.path.join(ROOT, "tools", "visual_audit.js"),
                                                              mimetype="text/javascript", max_age=0))


@app.after_request
def allow_audit_frame(response):
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY.replace("frame-ancestors 'none'",
                                                                                  "frame-ancestors 'self'")
    return response


if __name__ == "__main__":
    app.run(port=PORT, debug=True, use_reloader=False)
