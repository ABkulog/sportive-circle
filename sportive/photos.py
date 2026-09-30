"""Turning uploaded photos into safe, small profile pictures."""
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


def make_avatar(data):
    """Any photo -> a 640x640 JPEG: rotated upright, cropped to a square around the center,
    and re-encoded from scratch, so hidden metadata (like the GPS location phones add) is gone.

    Raises ValueError with a friendly message if the file isn't a usable photo.
    """
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ValueError
            if image.format in ("JPEG", "MPO"):
                image.draft("RGB", (AVATAR_SIZE * 2, AVATAR_SIZE * 2))
            elif image.width * image.height > MAX_FULL_DECODE_PIXELS:
                raise ValueError(TOO_BIG)
            image = ImageOps.exif_transpose(image)  # phones store "rotate me" in metadata
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            else:
                image = image.convert("RGB")
            image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
            output = BytesIO()
            image.save(output, "JPEG", quality=85, optimize=True)
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
