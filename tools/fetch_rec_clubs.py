"""Save a copy of every UW sports club (UW Rec's Clubs Offered page + HuskyLink's Sports/Recreation groups) in
sportive/data/uw_rec_clubs.json, for when those sites are down. The site itself reads them every day (clubsync.py).

    .venv/bin/python tools/fetch_rec_clubs.py
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sportive.clubsources import build_listing  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sportive", "data", "uw_rec_clubs.json")


def main():
    listing = build_listing()
    with open(OUT, "w", encoding="utf-8") as out:
        json.dump({**listing, "checked": date.today().isoformat()}, out, indent=1, ensure_ascii=False)
        out.write("\n")
    clubs = listing["clubs"]
    print(f"{len(clubs)} clubs written to {OUT}: {sum(c['source'] == 'uw_rec' for c in clubs)} from UW Rec, "
          f"{sum(c['source'] == 'huskylink' for c in clubs)} more from HuskyLink")


if __name__ == "__main__":
    main()
