"""Draws the home-screen icon: a white S and a gold C on UW purple (the team's SC logo).

    .venv/bin/python tools/make_icon.py 180 sportive/static/apple-touch-icon.png 192 sportive/static/icon-192.png 512 sportive/static/icon-512.png

Needs macOS (the font comes with it).
"""
import sys
from PIL import Image, ImageDraw, ImageFont

FONT, FONT_INDEX = "/System/Library/Fonts/Supplemental/PTSans.ttc", 4  # PT Sans Caption Bold (comes with macOS)
PURPLE, GOLD, WHITE = (75, 46, 131), (203, 189, 147), (255, 255, 255)


def draw(size, letter_height=0.40, gap=0.015):
    big = 1080
    img = Image.new("RGB", (big, big), PURPLE)
    d = ImageDraw.Draw(img)
    font_size = 400
    while True:  # grow the font until the capitals are letter_height of the icon
        font = ImageFont.truetype(FONT, font_size, index=FONT_INDEX)
        box = d.textbbox((0, 0), "SC", font=font)
        if box[3] - box[1] >= letter_height * big:
            break
        font_size += 4
    s, c = d.textbbox((0, 0), "S", font=font), d.textbbox((0, 0), "C", font=font)
    space = gap * big
    total = (s[2] - s[0]) + space + (c[2] - c[0])
    x = (big - total) / 2
    top = (big - (box[3] - box[1])) / 2 - box[1]
    d.text((x - s[0], top), "S", font=font, fill=WHITE)
    d.text((x + (s[2] - s[0]) + space - c[0], top), "C", font=font, fill=GOLD)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    for size, path in zip(map(int, sys.argv[1::2]), sys.argv[2::2]):
        draw(size).save(path, optimize=True)
