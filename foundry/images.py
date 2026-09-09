"""Bounded raster normalization and verification of frozen image derivatives.

Only uploads normalize pixels. Reports and exporters read a digest-bound PNG;
they never reopen the original to reinterpret orientation or metadata.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import warnings

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from .errors import DomainError

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_EDGE = 8192
MAX_IMAGE_PIXELS = 16_000_000


def _dimensions(size):
    width, height = size
    if min(width, height) < 1 or max(width, height) > MAX_IMAGE_EDGE or width * height > MAX_IMAGE_PIXELS:
        raise DomainError('IMAGE_LIMIT', 'Images must fit within 8,192 pixels per side and 16 million pixels in total.')


def normalize_image(data: bytes, format_hint=None):
    """Return a self-contained PNG and JSON-safe inspection metadata."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise DomainError('IMAGE_LIMIT', 'Supply a nonempty PNG or JPEG no larger than 20 MB.')
    expected = {'png': 'PNG', 'jpg': 'JPEG', 'jpeg': 'JPEG'}.get(str(format_hint).lower())
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in {'PNG', 'JPEG'} or (expected and original.format != expected):
                    raise DomainError('IMAGE_FORMAT_INVALID', 'The image bytes must match a supported PNG or JPEG file extension.')
                _dimensions(original.size)
                if getattr(original, 'n_frames', 1) != 1:
                    raise DomainError('IMAGE_ANIMATION_UNSUPPORTED', 'Animated and multi-frame images are not supported. Supply one still image.')
                original_format, original_size = original.format, original.size
                original.verify()
            with Image.open(BytesIO(data)) as decoded:
                decoded.load()  # Also rejects truncated JPEG pixel streams.
                oriented = ImageOps.exif_transpose(decoded)
                _dimensions(oriented.size)
                has_alpha = oriented.mode in {'RGBA', 'LA'} or 'transparency' in oriented.info
                rgba = oriented.convert('RGBA') if has_alpha else None
                profile = oriented.info.get('icc_profile')
                if profile:
                    try:
                        color_source = oriented if oriented.mode in {'RGB', 'CMYK', 'L'} else oriented.convert('RGB')
                        pixels = ImageCms.profileToProfile(color_source, ImageCms.ImageCmsProfile(BytesIO(profile)),
                                                           ImageCms.createProfile('sRGB'), outputMode='RGB')
                        if rgba is not None:
                            pixels.putalpha(rgba.getchannel('A'))
                    except (OSError, ValueError, TypeError, ImageCms.PyCMSError) as exc:
                        raise DomainError('IMAGE_COLOR_PROFILE', 'The embedded color profile could not be converted to sRGB.') from exc
                else:
                    pixels = rgba if rgba is not None else oriented.convert('RGB')
                # Reconstruct from pixels to remove EXIF, comments, ICC and PNG text.
                clean = Image.frombytes(pixels.mode, pixels.size, pixels.tobytes())
                output = BytesIO()
                clean.save(output, format='PNG', compress_level=9)
                result = output.getvalue()
                if len(result) > MAX_IMAGE_BYTES:
                    raise DomainError('IMAGE_LIMIT', 'The normalized PNG exceeds 20 MB. Supply a smaller image.')
                return result, {
                    'width_px': clean.width, 'height_px': clean.height,
                    'render_digest': sha256(result).hexdigest(), 'media_type': 'image/png',
                    'normalization': 'exif_transpose_strip_metadata_png',
                    'color_conversion': 'embedded_profile_to_srgb' if profile else 'rgb_without_embedded_profile',
                    'original_format': original_format.lower(),
                    'original_width_px': original_size[0], 'original_height_px': original_size[1],
                    'has_alpha': has_alpha, 'render_size': len(result),
                }
    except DomainError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise DomainError('IMAGE_LIMIT', 'The image exceeds the supported decoded pixel limit.') from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError) as exc:
        raise DomainError('IMAGE_FORMAT_INVALID', 'The image is invalid, truncated, or cannot be decoded safely.') from exc


def verify_render_image(data, render_digest, width_px, height_px):
    """Verify frozen content without color conversion, rotation or normalization."""
    if not data or len(data) > MAX_IMAGE_BYTES or sha256(data).hexdigest() != render_digest:
        raise DomainError('IMAGE_INTEGRITY', 'The image bytes no longer match their frozen identity.', 409)
    try:
        with Image.open(BytesIO(data)) as image:
            _dimensions(image.size)
            if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1 or image.size != (width_px, height_px):
                raise DomainError('IMAGE_INTEGRITY', 'The frozen image format or dimensions do not match the report.', 409)
            image.verify()
    except DomainError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError) as exc:
        raise DomainError('IMAGE_INTEGRITY', 'The frozen PNG could not be verified.', 409) from exc
    return data
