"""Categories, places and levels used across the app.

Edit these lists to change what students can pick. Sport keys are stored in the
database, so only change a key if there is no data using it yet; labels are
safe to change any time.
"""

# Alphabetical (Other last), because that's the order every dropdown shows them in.
SPORTS = {
    "archery": "Archery",
    "badminton": "Badminton",
    "baseball": "Baseball",
    "basketball": "Basketball",
    "biking": "Biking",
    "bowling": "Bowling",
    "boxing": "Boxing",
    "bjj": "Brazilian Jiu-Jitsu",
    "climbing": "Climbing",
    "cricket": "Cricket",
    "disc_golf": "Disc Golf",
    "dodgeball": "Dodgeball",
    "equestrian": "Equestrian",
    "esports": "Esports",
    "fencing": "Fencing",
    "field_hockey": "Field Hockey",
    "figure_skating": "Figure Skating",
    "football": "Football",
    "golf": "Golf",
    "gym": "Gym Buddy",
    "gymnastics": "Gymnastics",
    "handball": "Handball",
    "hiking": "Hiking",
    "ice_hockey": "Ice Hockey",
    "judo": "Judo",
    "karate": "Karate",
    "kendo": "Kendo",
    "lacrosse": "Lacrosse",
    "muay_thai": "Muay Thai / Kickboxing",
    "pickleball": "Pickleball",
    "racquetball": "Racquetball",
    "rowing": "Rowing / Kayaking",
    "rugby": "Rugby",
    "running": "Running",
    "sailing": "Sailing",
    "skateboarding": "Skateboarding",
    "snow": "Skiing / Snowboarding",
    "soccer": "Soccer",
    "softball": "Softball",
    "spikeball": "Spikeball",
    "squash": "Squash",
    "swimming": "Swimming",
    "table_tennis": "Table Tennis",
    "taekwondo": "Taekwondo",
    "tennis": "Tennis",
    "triathlon": "Triathlon",
    "ultimate": "Ultimate Frisbee",
    "volleyball": "Volleyball",
    "water_polo": "Water Polo",
    "weightlifting": "Weightlifting / Powerlifting",
    "wrestling": "Wrestling",
    "other": "Other",
}

# The place a host should check is free before posting a game ("check the courts are free").
SPORT_SPACE = {
    "basketball": "courts", "pickleball": "courts", "tennis": "courts", "volleyball": "courts",
    "soccer": "field", "football": "field", "ultimate": "field", "spikeball": "spot",
    "running": "trail", "hiking": "trail", "biking": "trail", "climbing": "wall", "gym": "gym",
    "rowing": "boathouse", "snow": "slopes", "esports": "room", "other": "place",
    # UW club sports
    "archery": "range", "badminton": "courts", "baseball": "field", "bowling": "lanes", "boxing": "mat room", "bjj": "mat room", "cricket": "field", "disc_golf": "course", "dodgeball": "gym", "equestrian": "stables", "fencing": "room", "field_hockey": "field", "figure_skating": "rink", "golf": "course", "gymnastics": "gym", "handball": "courts", "ice_hockey": "rink", "judo": "mat room", "karate": "mat room", "kendo": "room", "lacrosse": "field", "muay_thai": "mat room", "racquetball": "court", "rugby": "field", "sailing": "dock", "skateboarding": "spot", "softball": "field", "squash": "court", "swimming": "pool", "table_tennis": "tables", "taekwondo": "mat room", "triathlon": "route", "water_polo": "pool", "weightlifting": "gym", "wrestling": "mat room",
}

SPORT_EMOJI = {
    "basketball": "🏀",
    "soccer": "⚽",
    "football": "🏈",
    "volleyball": "🏐",
    "spikeball": "🟡",
    "ultimate": "🥏",
    "tennis": "🎾",
    "pickleball": "🏓",
    "running": "🏃",
    "climbing": "🧗",
    "gym": "🏋️",
    "rowing": "🚣",
    "snow": "🏂",
    "hiking": "🥾",
    "biking": "🚴",
    "esports": "🎮",
    "archery": "🏹",
    "badminton": "🏸",
    "baseball": "⚾",
    "bowling": "🎳",
    "boxing": "🥊",
    "bjj": "🥋",
    "cricket": "🏏",
    "disc_golf": "🥏",
    "dodgeball": "🤾",
    "equestrian": "🏇",
    "fencing": "🤺",
    "field_hockey": "🏑",
    "figure_skating": "⛸️",
    "golf": "⛳",
    "gymnastics": "🤸",
    "handball": "🤾",
    "ice_hockey": "🏒",
    "judo": "🥋",
    "karate": "🥋",
    "kendo": "🥋",
    "lacrosse": "🥍",
    "muay_thai": "🥊",
    "racquetball": "🎾",
    "rugby": "🏉",
    "sailing": "⛵",
    "skateboarding": "🛹",
    "softball": "🥎",
    "squash": "🎾",
    "swimming": "🏊",
    "table_tennis": "🏓",
    "taekwondo": "🥋",
    "triathlon": "🏊",
    "water_polo": "🤽",
    "weightlifting": "🏋️",
    "wrestling": "🤼",
    "other": "🏅",
}

# Alphabetical ("The Quad" under Q), with Off campus and Online last.
LOCATIONS = [
    "Burke-Gilman Trail",
    "Denny Field",
    "Emerald City Boxing Gym (Roosevelt)",
    "Fitness Center West (under Elm Hall)",
    "Green Lake Park pickleball courts",
    "The HUB (Husky Union Building)",
    "Hec Edmundson Pavilion",
    "Husky Track",
    "IMA (Intramural Activities Building)",
    "IMA Archery Room",
    "IMA Mat Rooms (martial arts)",
    "IMA North Tennis Courts",
    "IMA Pool",
    "IMA South Tennis Courts",
    "IMA Squash & Racquetball Courts",
    "The Quad",
    "Recreation Field 1 (by the IMA)",
    "Recreation Field 2 (by Husky Track)",
    "Recreation Field 3 (by the golf range)",
    "Recreation Field 4 (by the golf range)",
    "Red Square",
    "Sand Volleyball Courts (by the IMA)",
    "UW Golf Driving Range",
    "Waterfront Activities Center (WAC)",
    "Off campus (see note)",
    "Online",
]

IMA = "IMA (Intramural Activities Building)"
# Rooms inside the IMA that clubs use (UW Recreation's IMA tour: washington.edu/ima/self-guided-tour-of-the-ima).
IMA_MATS = "IMA Mat Rooms (martial arts)"          # Mat Rooms A & B: martial arts and movement clubs
IMA_POOL = "IMA Pool"                              # 14-lane pool: swimming and water polo
IMA_ARCHERY = "IMA Archery Room"                   # room 106: where the archery club shoots
IMA_COURTS = "IMA Squash & Racquetball Courts"     # squash (4 international courts), racquetball, handball
SAND_COURTS = "Sand Volleyball Courts (by the IMA)"
GOLF_RANGE = "UW Golf Driving Range"
RED_SQUARE = "Red Square"
BOXING_GYM = "Emerald City Boxing Gym (Roosevelt)"  # 6516 Roosevelt Way NE: where the UW Boxing Club trains
# UW Recreation's outdoor courts: South #1-7 (lit at night), North #8-13 (#11 and #12 have pickleball lines).
IMA_NORTH_COURTS = "IMA North Tennis Courts"
IMA_SOUTH_COURTS = "IMA South Tennis Courts"
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
# Seattle Parks' free public pickleball hub, where the Husky Pickleball Club also plays (about 2 miles north of campus).
GREEN_LAKE_PICKLEBALL = "Green Lake Park pickleball courts"
OFF_CAMPUS = "Off campus (see note)"
ONLINE = "Online"
HUB = "The HUB (Husky Union Building)"  # the student union: its games area is where esports meet up

# Opening hours: a game can't be posted at a place while it's closed. Each place has seasons, each with
# hours per weekday (0 = Monday): (opens, closes) as "HH:MM", or None = closed all day. A date outside every
# season, or a place not listed (fields, the Quad, Red Square, the trail...: no posted hours), has no limit.
# Sources, checked Oct 2026 (UW Rec hadn't posted Autumn 2026 hours yet, so its Autumn 2025 hours are used;
# update these when washington.edu/ima/facility-hours/ shows the new quarter):
#   IMA and its rooms: washington.edu/ima/?p=29656 (Autumn 2025). Pool: closes 30 min before the building
#   (washington.edu/ima/ima-pool/open-rec-offerings/). South tennis courts: lights off 30 min before the IMA closes
#   (washington.edu/ima/ima-building/facility-field-reservations/). Golf range and WAC: UW Rec, Autumn 2025.
#   Fitness Center West: hfs.uw.edu/perks-recreation/fcw (2026-27). Green Lake: Seattle park hours, 4 AM-11:30 PM.
ALL_YEAR = ("01-01", "12-31")
_WEEKDAYS, _WEEKEND = range(5), (5, 6)


def _week(weekdays, weekend):
    return {**{day: weekdays for day in _WEEKDAYS}, **{day: weekend for day in _WEEKEND}}


_IMA = _week(("06:00", "22:30"), ("09:00", "20:30"))
PLACE_HOURS = {
    IMA: [(ALL_YEAR, _IMA)],
    IMA_ARCHERY: [(ALL_YEAR, _IMA)],
    IMA_MATS: [(ALL_YEAR, _IMA)],
    IMA_COURTS: [(ALL_YEAR, _IMA)],
    IMA_POOL: [(ALL_YEAR, _week(("06:00", "22:00"), ("09:00", "20:00")))],
    IMA_SOUTH_COURTS: [(ALL_YEAR, _week(("00:00", "22:00"), ("00:00", "20:00")))],  # only the lights-off time
    FITNESS_WEST: [(ALL_YEAR, _week(("07:00", "23:00"), ("10:00", "20:00")))],
    GOLF_RANGE: [(("10-01", "10-31"), {0: None, **{day: ("10:00", "19:00") for day in range(1, 7)}}),
                 (("11-01", "11-30"), {0: None, 1: None, **{day: ("10:00", "18:00") for day in range(2, 7)}})],
    WAC: [(("10-01", "10-12"), {**{day: None for day in _WEEKDAYS}, 5: ("10:00", "18:00"), 6: ("10:00", "18:00")}),
          (("10-13", "12-31"), {day: None for day in range(7)}),      # closed for the season
          (("01-01", "03-31"), {day: None for day in range(7)})],
    GREEN_LAKE_PICKLEBALL: [(ALL_YEAR, {day: ("04:00", "23:30") for day in range(7)})],
}


# Map pins (latitude, longitude), from OpenStreetMap (openstreetmap.org), checked Sept 2026
# against UW Recreation's official field map (Recreation Field 1 is right north of the IMA,
# Field 2 is north of Husky Track, Fields 3 & 4 are by the golf range).
# None = no single pin (a long trail, or not in OpenStreetMap yet): the app shows a
# "search in Maps" link instead. Off campus / Online have no map at all.
LOCATION_COORDS = {
    IMA: (47.653743, -122.301231),
    IMA_NORTH_COURTS: (47.654870, -122.301420),  # the 6 courts just north of the IMA
    IMA_SOUTH_COURTS: (47.652894, -122.301170),  # the 7 courts just south of the IMA
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
    GREEN_LAKE_PICKLEBALL: (47.681547, -122.328384),  # next to the Green Lake Community Center
    HUB: (47.655500, -122.305100),            # the Husky Union Building, on Stevens Way
    IMA_MATS: (47.653743, -122.301231),       # inside the IMA
    IMA_POOL: (47.653743, -122.301231),
    IMA_ARCHERY: (47.653743, -122.301231),
    IMA_COURTS: (47.653743, -122.301231),
    SAND_COURTS: (47.654300, -122.300100),    # next to the IMA
    GOLF_RANGE: (47.661100, -122.296500),     # NE Clark Rd, past Rec Fields 3 and 4
    RED_SQUARE: (47.655900, -122.309600),
    BOXING_GYM: (47.676600, -122.317500),     # 6516 Roosevelt Way NE
}

# Open grass/turf areas, good for field sports like soccer and frisbee.
OPEN_FIELDS = [DENNY, QUAD, TRACK, REC_FIELD_1, REC_FIELD_2, REC_FIELD_3, REC_FIELD_4]

# Where each sport can actually be played. The event forms only offer these places,
# and the server rejects any other combination.
SPORT_LOCATIONS = {
    "basketball": [IMA, OFF_CAMPUS],
    "soccer": OPEN_FIELDS + [OFF_CAMPUS],
    "football": OPEN_FIELDS + [OFF_CAMPUS],
    "volleyball": OPEN_FIELDS + [IMA, SAND_COURTS, OFF_CAMPUS],  # indoor courts in Gym C, sand courts outside
    "spikeball": OPEN_FIELDS + [IMA, OFF_CAMPUS],
    "ultimate": OPEN_FIELDS + [OFF_CAMPUS],
    "tennis": [IMA_SOUTH_COURTS, IMA_NORTH_COURTS, OFF_CAMPUS],
    "pickleball": [IMA_NORTH_COURTS, IMA, GREEN_LAKE_PICKLEBALL, OFF_CAMPUS],  # IMA = indoor, in Gym B
    "running": OPEN_FIELDS + [TRAIL, RED_SQUARE, OFF_CAMPUS],   # the running club meets on the Quad
    "climbing": [IMA, OFF_CAMPUS],                             # the Crags climbing center is in the IMA
    "gym": [IMA, FITNESS_WEST, OFF_CAMPUS],
    "rowing": [WAC, OFF_CAMPUS],
    "snow": [OFF_CAMPUS],
    "hiking": [OFF_CAMPUS],
    "biking": [TRAIL, OFF_CAMPUS],
    "esports": [HUB, ONLINE, OFF_CAMPUS],
    # UW club sports
    "archery": [IMA_ARCHERY, OFF_CAMPUS],
    "badminton": [IMA, OFF_CAMPUS],                            # Gym B is the badminton gym
    "baseball": OPEN_FIELDS + [OFF_CAMPUS],
    "bowling": [OFF_CAMPUS],
    "boxing": [IMA, IMA_MATS, BOXING_GYM, OFF_CAMPUS],         # IMA: heavy bags in the conditioning room
    "bjj": [IMA, IMA_MATS, OFF_CAMPUS],
    "cricket": OPEN_FIELDS + [OFF_CAMPUS],
    "disc_golf": OPEN_FIELDS + [OFF_CAMPUS],
    "dodgeball": OPEN_FIELDS + [IMA, OFF_CAMPUS],
    "equestrian": [OFF_CAMPUS],                                # lessons at a nearby barn
    "fencing": OPEN_FIELDS + [IMA, IMA_MATS, RED_SQUARE, OFF_CAMPUS],
    "field_hockey": OPEN_FIELDS + [OFF_CAMPUS],
    "figure_skating": [OFF_CAMPUS],
    "golf": [GOLF_RANGE, OFF_CAMPUS],
    "gymnastics": [IMA, IMA_MATS, OFF_CAMPUS],
    "handball": [IMA_COURTS, IMA, OFF_CAMPUS],
    "ice_hockey": [OFF_CAMPUS],
    "judo": [IMA, IMA_MATS, OFF_CAMPUS],
    "karate": [IMA, IMA_MATS, OFF_CAMPUS],
    "kendo": [IMA, IMA_MATS, OFF_CAMPUS],
    "lacrosse": OPEN_FIELDS + [OFF_CAMPUS],
    "muay_thai": [IMA, IMA_MATS, OFF_CAMPUS],
    "racquetball": [IMA_COURTS, OFF_CAMPUS],
    "rugby": OPEN_FIELDS + [OFF_CAMPUS],
    "sailing": [WAC, OFF_CAMPUS],
    "skateboarding": [OFF_CAMPUS],
    "softball": OPEN_FIELDS + [OFF_CAMPUS],
    "squash": [IMA_COURTS, OFF_CAMPUS],
    "swimming": [IMA_POOL, WAC, OFF_CAMPUS],                   # WAC: open-water swims on Union Bay
    "table_tennis": [IMA, HUB, OFF_CAMPUS],
    "taekwondo": [IMA, IMA_MATS, OFF_CAMPUS],
    "triathlon": [IMA_POOL, TRACK, TRAIL, WAC, OFF_CAMPUS],
    "water_polo": [IMA_POOL, OFF_CAMPUS],
    "weightlifting": [IMA, FITNESS_WEST, OFF_CAMPUS],
    "wrestling": [IMA, IMA_MATS, OFF_CAMPUS],
    "other": LOCATIONS,
}
# Each sport's places in the same (alphabetical) order as the full list.
SPORT_LOCATIONS = {sport: sorted(places, key=LOCATIONS.index) for sport, places in SPORT_LOCATIONS.items()}

# Hosts pick how many players they need, whatever the sport (every game is different), or tick "No limit"
# (hall runs, club socials). This is only a sanity limit against typos for games that do set a number.
MAX_PLAYERS = 1000

# Team vs team: the sizes that make sense for each sport (players per team). Sports that aren't played as two
# teams (running, hiking, the gym...) aren't listed, so they don't offer team vs team at all.
SPORT_TEAM_SIZES = {
    "basketball": [2, 3, 4, 5],
    "soccer": [5, 6, 7, 8, 9, 10, 11],
    "football": [5, 6, 7, 8, 9, 10, 11],
    "volleyball": [2, 3, 4, 6],
    "spikeball": [2],
    "ultimate": [4, 5, 6, 7],
    "tennis": [2],
    "pickleball": [2],
    "esports": [2, 3, 4, 5],
    "badminton": [2],
    "baseball": [9],
    "cricket": [11],
    "dodgeball": [6],
    "field_hockey": [7, 11],
    "handball": [2],
    "ice_hockey": [5, 6],
    "lacrosse": [6, 10],
    "rugby": [7, 15],
    "softball": [9, 10],
    "table_tennis": [2],
    "water_polo": [7],
    "other": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
}

# The usual group size, suggested in the "Players" box (the host can type any number).
DEFAULT_PLAYERS = {
    "basketball": 10, "soccer": 14, "football": 14, "volleyball": 12, "spikeball": 4, "ultimate": 14,
    "tennis": 4, "pickleball": 4, "running": 6, "climbing": 4, "gym": 2, "rowing": 4, "snow": 4,
    "hiking": 6, "biking": 6, "esports": 5, "other": 10,
    "archery": 6, "badminton": 4, "baseball": 18, "bowling": 6, "boxing": 8, "bjj": 8, "cricket": 22, "disc_golf": 4, "dodgeball": 12, "equestrian": 4, "fencing": 6, "field_hockey": 14, "figure_skating": 6, "golf": 4, "gymnastics": 6, "handball": 4, "ice_hockey": 12, "judo": 8, "karate": 8, "kendo": 8, "lacrosse": 12, "muay_thai": 8, "racquetball": 2, "rugby": 14, "sailing": 4, "skateboarding": 4, "softball": 18, "squash": 2, "swimming": 6, "table_tennis": 4, "taekwondo": 8, "triathlon": 6, "water_polo": 14, "weightlifting": 2, "wrestling": 8,
}

SKILL_LEVELS = ["All levels", "Casual", "Intermediate", "Competitive"]
# Club events can be for any mix of these (saved as "Casual, Intermediate"); none or all of them is "All levels".
CLUB_LEVELS = SKILL_LEVELS[1:]

# "Open to": a game can be for everyone (the default) or, like UW Recreation's women-only hours, for a group.
# Same choices as clubs. Someone whose profile says a gender outside the group can't join; people who left
# gender blank (it's optional) are asked to confirm instead, so nobody is guessed about.
OPEN_TO = {"everyone": "Anyone", "women": "Women", "men": "Men", "nonbinary": "Nonbinary",  # what hosts can pick
           "other": "Other"}
# "Women & nonbinary" isn't offered anymore; games and clubs that already use it keep working.
OPEN_TO_LABELS = {**OPEN_TO, "women_nb": "Women & nonbinary"}
OPEN_TO_GENDERS = {"women": {"woman"}, "men": {"man"}, "nonbinary": {"nonbinary"}, "other": {"other"},
                   "women_nb": {"woman", "nonbinary"}}
# How a group reads in a sentence ("This game is for ...") and on a badge.
OPEN_TO_PHRASE = {"women": "women", "men": "men", "nonbinary": "nonbinary players", "other": "people who chose Other",
                  "women_nb": "women & nonbinary players"}
OPEN_TO_BADGE = {"women": "Women only", "men": "Men only", "nonbinary": "Nonbinary only", "other": "Other only",
                 "women_nb": "Women & nonbinary"}
STATED_GENDERS = {"woman", "man", "nonbinary"}  # "Other" and blank never block anyone (they confirm instead)

# How long one event can last, in hours. Trips (a hike, a day on the slopes, a bike ride) can take days;
# a pickup game can't. (Testers asked why a Spikeball game could be 24 hours long.)
DEFAULT_MAX_HOURS = 6
SPORT_MAX_HOURS = {"hiking": 72, "snow": 72, "biking": 72, "rowing": 12, "running": 12, "esports": 12, "other": 72,
                   "cricket": 8, "equestrian": 12, "sailing": 12, "triathlon": 12}

# "Need players" quick posts: (minutes from now, label)
QUICK_START_OPTIONS = [(0, "Right now"), (15, "In 15 min"), (30, "In 30 min"), (60, "In 1 hour"), (120, "In 2 hours")]
QUICK_DURATIONS = [(30, "30 min"), (60, "1 hour"), (90, "1.5 hours"), (120, "2 hours")]

# Good-to-know details for a sport at a place, shown when picking the place and on the event page.
# From UW Recreation's courts page (washington.edu/ima/ima-building/facility-field-reservations) and
# Seattle Parks (greenlakepickleball.org), checked Sept 2026.
PLACE_TIPS = {
    ("pickleball", IMA_NORTH_COURTS): "Court 12 is for pickleball and court 11 is shared with tennis. "
                                      "First come, first served.",
    ("pickleball", IMA): "Indoor pickleball is in Gym B, Thursdays 2-5 PM. Needs an IMA membership.",
    ("pickleball", GREEN_LAKE_PICKLEBALL): "Free public courts next to the Green Lake Community Center, "
                                           "open play every day. About 2 miles north of campus.",
    ("tennis", IMA_SOUTH_COURTS): "Courts 1-7. They have lights for evening games.",
    ("tennis", IMA_NORTH_COURTS): "Courts 8-13. Court 12 is for pickleball.",
    # Club spaces (UW Recreation's IMA tour and club pages, checked Oct 2026).
    ("boxing", BOXING_GYM): "Where the UW Boxing Club trains: 6516 Roosevelt Way NE, about a mile north of campus.",
    ("boxing", IMA): "The IMA's conditioning room has speed and heavy bags. Needs an IMA membership.",
    ("archery", IMA_ARCHERY): "Room 106 in the IMA, where the archery club shoots. Needs an IMA membership.",
    ("swimming", IMA_POOL): "14-lane pool in the IMA. Check lap-swim hours; needs an IMA membership.",
    ("water_polo", IMA_POOL): "14-lane pool in the IMA. Check the pool schedule; needs an IMA membership.",
    ("triathlon", IMA_POOL): "14-lane pool in the IMA. Check lap-swim hours; needs an IMA membership.",
    ("badminton", IMA): "Gym B is the IMA's badminton gym. Needs an IMA membership.",
    ("volleyball", IMA): "Gym C is the IMA's volleyball gym. Needs an IMA membership.",
    ("climbing", IMA): "The Crags climbing center: a 42-foot wall and a bouldering area. Needs an IMA membership.",
    ("golf", GOLF_RANGE): "UW's driving range on NE Clark Rd, past Rec Fields 3 and 4.",
    ("bjj", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("judo", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("karate", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("kendo", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("muay_thai", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("taekwondo", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("wrestling", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("fencing", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("gymnastics", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("boxing", IMA_MATS): "Mat Rooms A and B in the IMA, used by martial arts clubs. Needs an IMA membership.",
    ("squash", IMA_COURTS): "Squash (4 international courts), racquetball and handball courts in the IMA.",
    ("racquetball", IMA_COURTS): "Squash (4 international courts), racquetball and handball courts in the IMA.",
    ("handball", IMA_COURTS): "Squash (4 international courts), racquetball and handball courts in the IMA.",
    ("fencing", RED_SQUARE): "Open plaza in the middle of campus. Bring your own gear and leave room for people walking.",
}
