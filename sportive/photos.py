"""Turning uploaded photos into safe, small pictures: profile photos, club logos and photos sent in chats."""
from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

AVATAR_SIZE = 640  # big enough to look sharp when someone taps a photo to see it large
MAX_UPLOAD_MB = 8
ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "GIF"}  # MPO = the JPEG variant some phones make

# Refuse absurdly large images (a tiny file can claim to be gigapixels and eat all the memory).
Image.MAX_IMAGE_PIXELS = 50_000_000
# JPEGs are decoded at a reduced size (draft mode), so big phone photos are cheap. Other formats are
# decoded in full: 16 MP is ~64 MB as RGBA, which a small server can afford; 50 MP (~200 MB) it can't.
MAX_FULL_DECODE_PIXELS = 16_000_000
TOO_BIG = "That picture is too big. Try a smaller one, or a screenshot of it."
NOT_A_PHOTO = "That file isn't a photo we can use. Try a JPG or PNG picture."


CHAT_PHOTO_SIZE = 1280  # the long side of a photo sent in a chat: sharp on a phone, ~150-300 KB


def make_avatar(data):
    """Any photo -> a 640x640 JPEG: rotated upright, cropped to a square around the center,
    and re-encoded from scratch, so hidden metadata (like the GPS location phones add) is gone.

    Raises ValueError with a friendly message if the file isn't a usable photo.
    """
    return _clean_photo(data, AVATAR_SIZE, square=True, quality=85)


def make_chat_photo(data):
    """A photo sent in a chat -> a JPEG at most 1280px on its long side, not cropped, upright, no hidden
    metadata (like where it was taken). Raises ValueError with a friendly message like make_avatar."""
    return _clean_photo(data, CHAT_PHOTO_SIZE, square=False, quality=80)


def _clean_photo(data, size, square, quality):
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ValueError
            if image.format in ("JPEG", "MPO"):
                image.draft("RGB", (size * 2, size * 2))
            elif image.width * image.height > MAX_FULL_DECODE_PIXELS:
                raise ValueError(TOO_BIG)
            image = ImageOps.exif_transpose(image)  # phones store "rotate me" in metadata
            if image.mode.startswith("I"):  # 16-bit (or 32-bit) grayscale: bring it down to 0-255, or it's all white
                low, high = image.getextrema()
                scale = 255 / (high - low) if high > low else 0
                image = image.point(lambda v: (v - low) * scale).convert("L")
            if image.mode in ("RGBA", "LA", "P", "PA") or "transparency" in image.info:  # see-through: on white
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            if square:
                image = ImageOps.fit(image, (size, size), Image.LANCZOS)
            else:
                image.thumbnail((size, size), Image.LANCZOS)  # keeps the shape; never makes it bigger
            output = BytesIO()
            image.save(output, "JPEG", quality=quality, optimize=True)
            return output.getvalue()
    except ValueError as error:
        raise ValueError(TOO_BIG if str(error) == TOO_BIG else NOT_A_PHOTO) from None
    except Image.DecompressionBombError:
        raise ValueError(TOO_BIG) from None
    except (UnidentifiedImageError, OSError):
        raise ValueError(NOT_A_PHOTO) from None


THUMB_SIZES = (96, 160)  # small circles in lists (up to 48px, and up to 80px on sharp phone screens)


@lru_cache(maxsize=512)
def thumbnail(jpeg, size):
    """A smaller copy of a 640px avatar (a few KB instead of 40-90), remembered for repeat requests."""
    with Image.open(BytesIO(jpeg)) as image:
        small = image.convert("RGB").resize((size, size), Image.LANCZOS)
        out = BytesIO()
        small.save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue()
