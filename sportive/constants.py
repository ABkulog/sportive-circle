"""Categories, places and levels used across the app.

Edit these lists to change what students can pick. Sport keys are stored in the
database, so only change a key if there is no data using it yet; labels are
safe to change any time.
"""

SPORTS = {
    "basketball": "Basketball",
    "soccer": "Soccer",
    "football": "Football",
    "volleyball": "Volleyball",
    "spikeball": "Spikeball",
    "ultimate": "Ultimate Frisbee",
    "tennis": "Tennis",
    "running": "Running",
    "climbing": "Climbing",
    "gym": "Gym Buddy",
    "rowing": "Rowing / Kayaking",
    "snow": "Skiing / Snowboarding",
    "hiking": "Hiking",
    "biking": "Biking",
    "esports": "Esports",
    "other": "Other",
}

SPORT_EMOJI = {
    "basketball": "🏀",
    "soccer": "⚽",
    "football": "🏈",
    "volleyball": "🏐",
    "spikeball": "🟡",
    "ultimate": "🥏",
    "tennis": "🎾",
    "running": "🏃",
    "climbing": "🧗",
    "gym": "🏋️",
    "rowing": "🚣",
    "snow": "🏂",
    "hiking": "🥾",
    "biking": "🚴",
    "esports": "🎮",
    "other": "🏅",
}

LOCATIONS = [
    "IMA (Intramural Activities Building)",
    "Fitness Center West (under Elm Hall)",
    "Recreation Field 1 (by the IMA)",
    "Recreation Field 2 (by Husky Track)",
    "Recreation Field 3 (by the golf range)",
    "Recreation Field 4 (by the golf range)",
    "Husky Track",
    "Waterfront Activities Center (WAC)",
    "Denny Field",
    "The Quad",
    "Hec Edmundson Pavilion",
    "Burke-Gilman Trail",
    "Off campus (see note)",
    "Online",
]

IMA = "IMA (Intramural Activities Building)"
FITNESS_WEST = "Fitness Center West (under Elm Hall)"
# UW's official names for the outdoor fields (they used to be called "IMA Sports Fields").
REC_FIELD_1 = "Recreation Field 1 (by the IMA)"
REC_FIELD_2 = "Recreation Field 2 (by Husky Track)"
REC_FIELD_3 = "Recreation Field 3 (by the golf range)"
REC_FIELD_4 = "Recreation Field 4 (by the golf range)"
TRACK = "Husky Track"
WAC = "Waterfront Activities Center (WAC)"
DENNY = "Denny Field"
QUAD = "The Quad"
TRAIL = "Burke-Gilman Trail"
OFF_CAMPUS = "Off campus (see note)"
ONLINE = "Online"

# Map pins (latitude, longitude), from OpenStreetMap (openstreetmap.org), checked Sept 2026
# against UW Recreation's official field map (Recreation Field 1 is right north of the IMA,
# Field 2 is north of Husky Track, Fields 3 & 4 are by the golf range).
# None = no single pin (a long trail, or not in OpenStreetMap yet): the app shows a
# "search in Maps" link instead. Off campus / Online have no map at all.
LOCATION_COORDS = {
    IMA: (47.653743, -122.301231),
    FITNESS_WEST: (47.656529, -122.315254),   # Elm Hall
    REC_FIELD_1: (47.654750, -122.300583),    # the turf field just north of the IMA
    REC_FIELD_2: (47.657727, -122.297914),    # north of Husky Track
    REC_FIELD_3: (47.660058, -122.295414),    # by the golf range, NE Clark Rd
    REC_FIELD_4: (47.660431, -122.293564),    # by the golf range, NE Clark Rd
    TRACK: (47.656746, -122.297181),          # "Husky Outdoor Track"
    WAC: (47.648534, -122.299694),            # the boat rental entrance
    DENNY: (47.659804, -122.305883),
    QUAD: (47.657285, -122.307213),
    "Hec Edmundson Pavilion": (47.652179, -122.302125),
    TRAIL: None,                              # a 20-mile trail: search instead of one pin
}

# Open grass/turf areas, good for field sports like soccer and frisbee.
OPEN_FIELDS = [DENNY, QUAD, TRACK, REC_FIELD_1, REC_FIELD_2, REC_FIELD_3, REC_FIELD_4]

# Where each sport can actually be played. The event forms only offer these places,
# and the server rejects any other combination.
SPORT_LOCATIONS = {
    "basketball": [IMA, OFF_CAMPUS],
    "soccer": OPEN_FIELDS + [OFF_CAMPUS],
    "football": OPEN_FIELDS + [OFF_CAMPUS],
    "volleyball": OPEN_FIELDS + [IMA, OFF_CAMPUS],  # outdoor fields + the IMA's indoor courts
    "spikeball": OPEN_FIELDS + [IMA, OFF_CAMPUS],
    "ultimate": OPEN_FIELDS + [OFF_CAMPUS],
    "tennis": [IMA, OFF_CAMPUS],
    "running": OPEN_FIELDS + [TRAIL, OFF_CAMPUS],   # sprints/intervals on the fields too
    "climbing": [IMA, OFF_CAMPUS],
    "gym": [IMA, FITNESS_WEST, OFF_CAMPUS],
    "rowing": [WAC, OFF_CAMPUS],
    "snow": [OFF_CAMPUS],
    "hiking": [OFF_CAMPUS],
    "biking": [TRAIL, OFF_CAMPUS],
    "esports": [ONLINE, OFF_CAMPUS],
    "other": LOCATIONS,
}

# Most players one event can have, including the host. First guesses: run
# `flask --app main sport-stats` once people are using the app and adjust these.
SPORT_MAX_PLAYERS = {
    "basketball": 10,   # 5v5
    "soccer": 22,       # 11v11
    "football": 22,     # 11v11 (most pickup games are smaller, like 7v7 flag)
    "volleyball": 12,   # 6v6
    "spikeball": 8,     # 2v2 per net; room for a second net or people rotating in
    "ultimate": 14,     # 7v7
    "tennis": 4,        # doubles
    "running": 20,
    "climbing": 8,
    "gym": 4,
    "rowing": 10,
    "snow": 10,
    "hiking": 15,
    "biking": 15,
    "esports": 10,
    "other": 30,
}

SKILL_LEVELS = ["All levels", "Casual", "Intermediate", "Competitive"]

# "Need players" quick posts: (minutes from now, label)
QUICK_START_OPTIONS = [(0, "Right now"), (15, "In 15 min"), (30, "In 30 min"), (60, "In 1 hour"), (120, "In 2 hours")]
QUICK_DURATIONS = [(30, "30 min"), (60, "1 hour"), (90, "1.5 hours"), (120, "2 hours")]
