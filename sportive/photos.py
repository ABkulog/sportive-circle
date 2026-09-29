"""Turning uploaded photos into safe, small profile pictures."""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

AVATAR_SIZE = 640  # big enough to look sharp when someone taps a photo to see it large
MAX_UPLOAD_MB = 8
ALLOWED_FORMATS = {"JPEG", "MPO", "PNG", "WEBP", "GIF"}  # MPO = the JPEG variant some phones make

# Refuse absurdly large images (a tiny file can claim to be gigapixels and eat all the memory).
Image.MAX_IMAGE_PIXELS = 50_000_000


def make_avatar(data):
    """Any photo -> a 640x640 JPEG: rotated upright, cropped to a square around the center,
    and re-encoded from scratch, so hidden metadata (like the GPS location phones add) is gone.

    Raises ValueError with a friendly message if the file isn't a usable photo.
    """
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ValueError
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
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise ValueError("That file isn't a photo we can use. Try a JPG or PNG picture.") from None
