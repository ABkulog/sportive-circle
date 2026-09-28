"""Make the QR codes in marketing/ (for flyers, posters and club group chats).

    .venv/bin/pip install segno        # only needed for this script
    .venv/bin/python tools/make_qr.py [URL]

Makes:
  marketing/qr-code.png        just the code (1200 x 1200), purple on white, gold paw in the middle
  marketing/qr-code.svg        the same code as a vector, for printing at any size
  marketing/qr-flyer.png       the code with a "Scan to join" caption, ready to print or post

If the site's address ever changes (e.g. a custom domain), run this again and replace printed flyers.
"""
import io
import os
import sys

import segno
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = sys.argv[1] if len(sys.argv) > 1 else "https://sportive-circle.onrender.com"
OUT = os.path.join(ROOT, "marketing")
PURPLE, GOLD, WHITE = "#4b2e83", "#ffc700", "#ffffff"


def paw(size):
    """The app's logo (same shapes as static/icon.svg): a gold paw on a purple circle."""
    scale = 4  # draw big, then shrink, for smooth edges
    s = size * scale
    k = s / 64
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse([2 * k, 2 * k, 62 * k, 62 * k], fill=PURPLE)
    draw.ellipse([4 * k, 4 * k, 60 * k, 60 * k], outline=GOLD, width=int(3 * k))

    def toe(cx, cy, rx, ry, angle):
        layer = Image.new("L", (s, s), 0)
        ImageDraw.Draw(layer).ellipse([(cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k], fill=255)
        image.paste(GOLD, mask=layer.rotate(-angle, center=(cx * k, cy * k)) if angle else layer)

    toe(32, 40, 10, 8.5, 0)
    for cx, cy, ry, angle in ((19.5, 29, 5.4, -20), (27.5, 21.5, 5.6, -6), (36.5, 21.5, 5.6, 6), (44.5, 29, 5.4, 20)):
        toe(cx, cy, 4.2, ry, angle)
    return image.resize((size, size), Image.LANCZOS)


def code_image(size):
    # Error correction "H" keeps the code readable even with the logo covering its middle.
    qr = segno.make(URL, error="h")
    buffer = io.BytesIO()
    qr.save(buffer, kind="png", scale=40, border=4, dark=PURPLE, light=WHITE)
    image = Image.open(buffer).convert("RGBA").resize((size, size), Image.NEAREST)
    logo_size = size // 5  # small enough that phones still read it easily
    ring = logo_size + size // 40
    x = (size - ring) // 2
    ImageDraw.Draw(image).ellipse([x, x, x + ring, x + ring], fill=WHITE)
    image.alpha_composite(paw(logo_size), ((size - logo_size) // 2, (size - logo_size) // 2))
    return image.convert("RGB"), qr


def font(size, bold=True):
    for path in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/Library/Fonts/Arial Bold.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def flyer(code):
    width, height = 1200, 1600
    image = Image.new("RGB", (width, height), WHITE)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 22], fill=PURPLE)
    draw.rectangle([int(width * .6), 0, width, 22], fill=GOLD)
    draw.text((width / 2, 130), "Sportive Circle", font=font(96), fill=PURPLE, anchor="mm")
    draw.text((width / 2, 225), "Find people to play sports with at UW.", font=font(46, bold=False), fill="#333333", anchor="mm")
    image.paste(code.resize((900, 900), Image.NEAREST), (150, 300))
    draw.text((width / 2, 1290), "Scan to join", font=font(84), fill=PURPLE, anchor="mm")
    draw.text((width / 2, 1380), URL.replace("https://", ""), font=font(40, bold=False), fill="#333333", anchor="mm")
    draw.text((width / 2, 1480), "For UW students. A student project, not an official UW service.",
              font=font(30, bold=False), fill="#666666", anchor="mm")
    return image


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    code, qr = code_image(1200)
    code.save(os.path.join(OUT, "qr-code.png"), optimize=True)
    qr.save(os.path.join(OUT, "qr-code.svg"), scale=10, border=4, dark=PURPLE, light=WHITE)
    flyer(code).save(os.path.join(OUT, "qr-flyer.png"), optimize=True)
    print(f"QR codes for {URL} saved in marketing/")
