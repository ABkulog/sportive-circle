"""Phone numbers typed with a country picker ("US +1", "UK +44"...) and a number box that adds dashes as you type.

Stored as one string with the country code, like +12065550142, so it can be texted or called anywhere.
Used for club registration (only admins see that number) and for texts (sms.py).
"""
import re

# (code, country, dialing code). The US first (most of us), then A-Z. The code is the <option> value, because
# some countries share a dialing code (the US and Canada are both +1).
COUNTRIES = [
    ("US", "United States", "1"),
    ("AR", "Argentina", "54"), ("AU", "Australia", "61"), ("BD", "Bangladesh", "880"), ("BR", "Brazil", "55"),
    ("CA", "Canada", "1"), ("CL", "Chile", "56"), ("CN", "China", "86"), ("CO", "Colombia", "57"),
    ("EG", "Egypt", "20"), ("ET", "Ethiopia", "251"), ("FR", "France", "33"), ("DE", "Germany", "49"),
    ("HK", "Hong Kong", "852"), ("IN", "India", "91"), ("ID", "Indonesia", "62"), ("IR", "Iran", "98"),
    ("IL", "Israel", "972"), ("IT", "Italy", "39"), ("JP", "Japan", "81"), ("KE", "Kenya", "254"),
    ("MY", "Malaysia", "60"), ("MX", "Mexico", "52"), ("NL", "Netherlands", "31"), ("NZ", "New Zealand", "64"),
    ("NG", "Nigeria", "234"), ("NO", "Norway", "47"), ("PK", "Pakistan", "92"), ("PE", "Peru", "51"),
    ("PH", "Philippines", "63"), ("RU", "Russia", "7"), ("SA", "Saudi Arabia", "966"), ("SG", "Singapore", "65"),
    ("ZA", "South Africa", "27"), ("KR", "South Korea", "82"), ("ES", "Spain", "34"), ("SE", "Sweden", "46"),
    ("TW", "Taiwan", "886"), ("TH", "Thailand", "66"), ("TR", "Türkiye", "90"), ("UA", "Ukraine", "380"),
    ("AE", "United Arab Emirates", "971"), ("GB", "United Kingdom", "44"), ("VN", "Vietnam", "84"),
]
DIAL = {code: dial for code, _, dial in COUNTRIES}


def phone_from_form(country, number):
    """The country picked and the number typed -> "+12065550142", or None if it isn't a phone number.
    A number typed with its own + code wins over the picker."""
    number = (number or "").strip()
    digits = re.sub(r"\D", "", number)
    if number.startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    dial = DIAL.get(country or "US")
    if dial is None:
        return None
    if dial == "1":  # US and Canada: 10 digits (a leading 1 is fine), area codes don't start with 0 or 1
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return f"+1{digits}" if len(digits) == 10 and digits[0] not in "01" else None
    if digits.startswith("00" + dial):  # typed the international prefix too
        digits = digits[2 + len(dial):]
    elif digits.startswith(dial) and len(digits) > 9:  # typed the country code again
        digits = digits[len(dial):]
    digits = digits[1:] if digits.startswith("0") else digits  # the "0" dialed only inside the country
    return f"+{dial}{digits}" if 6 <= len(digits) and len(dial) + len(digits) <= 15 else None


def group_digits(digits, us=False):
    """206-555-0142 for the US and Canada; other numbers in groups of 3 with the last 4 together."""
    if us:
        parts = [digits[:3], digits[3:6], digits[6:10]]
    else:
        head, tail = digits[:-4], digits[-4:]
        parts = [head[i:i + 3] for i in range(0, len(head), 3)]
        if len(parts) > 1 and len(parts[-1]) == 1:  # no lonely digit: 079-4609 instead of 079-460-9
            parts[-2:] = [parts[-2] + parts[-1]]
        parts.append(tail)
    return "-".join(part for part in parts if part)


def split_phone(phone):
    """"+12065550142" -> ("US", "206-555-0142"), for filling the form back in. Unknown codes stay whole."""
    if not phone:
        return "US", ""
    for code, _, dial in COUNTRIES:  # the US comes first, so +1 picks it (Canada looks the same)
        if phone.startswith("+" + dial):
            return code, group_digits(phone[1 + len(dial):], us=dial == "1")
    return "US", phone


def pretty_phone(phone):
    """"+12065550142" -> "+1 206-555-0142" (for admins, and for your own number in Settings)."""
    if not phone:
        return ""
    code, national = split_phone(phone)
    return f"+{DIAL[code]} {national}" if phone.startswith("+" + DIAL[code]) else phone
