"""Tell everyone already on the app that they can get updates by text now (one email each, once).

Run it on the server (Render -> your service -> Shell), after the TWILIO_* settings are in place:

    python tools/announce_texts.py           # dry run: says how many people would get it, sends nothing
    python tools/announce_texts.py --send    # sends the emails

Safe to run again: people who already got it are skipped. People who already added a number are skipped too.
They also see a "New: game updates by text" card on Home until they add a number or tap Not now.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sportive import create_app  # noqa: E402
from sportive.announcements import announce_texts  # noqa: E402


def main():
    send = "--send" in sys.argv[1:]
    app = create_app()
    with app.app_context():
        try:
            count, failed = announce_texts(send=send)
        except RuntimeError as error:
            print(error)
            return 1
    if not send:
        print(f"Dry run: {count} people would get the texts email. Add --send to send it.")
    else:
        print(f"Sent to {count} people." + (f" {failed} failed (run again later to retry them)." if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
