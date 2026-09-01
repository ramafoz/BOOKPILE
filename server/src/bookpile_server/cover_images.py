from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .config import Settings


register_heif_opener()
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}


class InvalidCoverImage(Exception):
    pass


@dataclass(frozen=True)
class ProcessedCover:
    content: bytes
    width_px: int
    height_px: int
    sha256: str


def process_cover_image(content: bytes, settings: Settings) -> ProcessedCover:
    if not content:
        raise InvalidCoverImage("Choose a cover image to upload.")
    if len(content) > settings.cover_max_upload_bytes:
        raise InvalidCoverImage("Cover images must be 12 MiB or smaller.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in ALLOWED_FORMATS:
                    raise InvalidCoverImage("Use a JPEG, PNG, WebP, HEIC or HEIF image.")
                if getattr(source, "n_frames", 1) != 1:
                    raise InvalidCoverImage("Animated or multi-page images are not supported.")
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > settings.cover_max_pixels:
                    raise InvalidCoverImage("This image has too many pixels to process safely.")
                source.load()
                image = ImageOps.exif_transpose(source)
                image.thumbnail(
                    (settings.cover_max_width, settings.cover_max_height),
                    Image.Resampling.LANCZOS,
                )
                if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                    rgba = image.convert("RGBA")
                    flattened = Image.new("RGB", rgba.size, "white")
                    flattened.paste(rgba, mask=rgba.getchannel("A"))
                    image = flattened
                else:
                    image = image.convert("RGB")
                output = BytesIO()
                image.save(
                    output,
                    format="WEBP",
                    quality=settings.cover_webp_quality,
                    method=6,
                )
                encoded = output.getvalue()
                return ProcessedCover(
                    content=encoded,
                    width_px=image.width,
                    height_px=image.height,
                    sha256=sha256(encoded).hexdigest(),
                )
    except InvalidCoverImage:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as exc:
        raise InvalidCoverImage("The selected file is not a valid supported cover image.") from exc
