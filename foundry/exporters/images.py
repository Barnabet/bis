"""Resolve immutable PNG assets into verified in-memory export inputs."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import re
import warnings
from typing import Callable
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000


@dataclass(frozen=True)
class BoundImage:
    data: bytes
    width_px: int
    height_px: int
    render_digest: str
    original_digest: str
    asset_id: str

    def fit(self, max_width: float, max_height: float, *, units_per_pixel: float) -> tuple[float, float]:
        """Fit physical dimensions without cropping, stretching or upscaling."""
        scale = min(units_per_pixel, max_width / self.width_px, max_height / self.height_px)
        return self.width_px * scale, self.height_px * scale

    def manifest(self, node: dict) -> dict:
        return {"asset_id": self.asset_id, "original_digest": self.original_digest,
                "render_digest": self.render_digest, "media_type": "image/png",
                "width_px": self.width_px, "height_px": self.height_px,
                "alt_text": node["alt_text"], "decorative": node.get("decorative", False),
                "pixel_content_editable": False, "crop": "none", "aspect_ratio_preserved": True}


def resolve_images(snapshot: dict, nodes: list[dict], resolver: Callable[[str], bytes] | None) -> dict[str, BoundImage]:
    # Import lazily to avoid a package initialization cycle.
    from . import ExportError
    image_nodes = [node for node in nodes if node["kind"] == "image"]
    if len(image_nodes) > MAX_IMAGES:
        raise ExportError(f"This export profile supports at most {MAX_IMAGES} bound report images.", "image_count_limit")
    assets = {asset["id"]: asset for asset in snapshot["source_assets"]}
    resolved, cache = {}, {}
    for node in image_nodes:
        digest = node.get("render_digest")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ExportError("The required report image has no frozen sanitized PNG identity.", "image_render_unavailable")
        if resolver is None:
            raise ExportError("The required report image needs the host's immutable asset resolver.", "image_resolver_required")
        if node.get("media_type") not in {None, "image/png"}:
            raise ExportError("The report image must reference a sanitized PNG.", "image_format_unsupported")
        asset = assets.get(node["asset_id"])
        if asset is None:
            raise ExportError("The report image has no bound original source asset.", "image_source_missing")
        if digest not in cache:
            try:
                data = resolver(digest)
            except Exception as error:
                raise ExportError("The frozen report image is unavailable from the immutable asset store.", "image_asset_unavailable") from error
            if not isinstance(data, bytes):
                raise ExportError("The immutable image resolver must return bytes.", "image_resolver_invalid")
            if len(data) > MAX_IMAGE_BYTES:
                raise ExportError("The frozen image exceeds the 20 MiB export limit.", "image_size_limit")
            if hashlib.sha256(data).hexdigest() != digest:
                raise ExportError("The report image bytes differ from their frozen digest.", "image_integrity")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(data)) as image:
                        if image.format != "PNG" or not data.startswith(b"\x89PNG\r\n\x1a\n"):
                            raise ExportError("The frozen report image is not a PNG.", "image_format_unsupported")
                        width, height = image.size
                        if width > 8192 or height > 8192 or width * height > MAX_IMAGE_PIXELS:
                            raise ExportError("The frozen image exceeds the normalized image dimensions limit.", "image_size_limit")
                        if getattr(image, "n_frames", 1) != 1:
                            raise ExportError("Animated PNGs are outside this image export profile.", "image_format_unsupported")
                        if image.info:
                            raise ExportError("The frozen PNG contains metadata that must be removed during image normalization.", "image_metadata_unsupported")
                        image.verify()
                    with Image.open(BytesIO(data)) as image:
                        image.load()
                        if image.mode not in {"RGB", "RGBA", "L", "LA"}:
                            raise ExportError("The image must be normalized to a supported PNG color mode.", "image_format_unsupported")
            except ExportError:
                raise
            except Exception as error:
                raise ExportError("The frozen PNG cannot be fully decoded.", "image_decode_failed") from error
            cache[digest] = data, width, height
        data, width, height = cache[digest]
        if (node["width_px"], node["height_px"]) != (width, height):
            raise ExportError("The decoded image dimensions differ from the frozen report node.", "image_dimensions_mismatch")
        resolved[node["id"]] = BoundImage(data, width, height, digest, asset["digest"], node["asset_id"])
    return resolved


def set_picture_properties(properties, node):
    """Set standard DrawingML alt/title properties and decorative metadata."""
    properties.set("descr", node["alt_text"])
    properties.set("title", node["title"])
    if node.get("decorative", False):
        main = "http://schemas.openxmlformats.org/drawingml/2006/main"
        decorative = "http://schemas.microsoft.com/office/drawing/2017/decorative"
        extension_list = properties.find(f"{{{main}}}extLst")
        if extension_list is None:
            extension_list = properties.makeelement(f"{{{main}}}extLst", {})
            properties.append(extension_list)
        uri = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
        if not any(child.get("uri") == uri for child in extension_list):
            extension = properties.makeelement(f"{{{main}}}ext", {"uri": uri})
            extension.append(properties.makeelement(f"{{{decorative}}}decorative", {"val": "1"}))
            extension_list.append(extension)


def annotate_workbook_images(path: Path, nodes: list[dict]):
    """Retain title and alt properties alongside XlsxWriter image placement.

    The core workbook's charts use graphic frames. Its picture elements are
    exclusively the bound report images, inserted in view order on Images.
    """
    from . import ExportError
    if not nodes:
        return
    with ZipFile(path) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    namespace = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
    pictures = []
    modified = {}
    names = sorted(name for name in parts if re.fullmatch(r"xl/drawings/drawing\d+\.xml", name))
    for name in names:
        root = ET.fromstring(parts[name])
        for picture in root.findall(f".//{{{namespace}}}pic"):
            properties = picture.find(f"{{{namespace}}}nvPicPr/{{{namespace}}}cNvPr")
            pictures.append((name, root, properties))
    if len(pictures) != len(nodes):
        raise ExportError("Workbook image coverage differs from its view.", "image_embedding_mismatch")
    for (name, root, properties), node in zip(pictures, nodes):
        set_picture_properties(properties, node)
        modified[name] = root
    for name, root in modified.items():
        parts[name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    replacement = path.with_suffix(".images.tmp")
    with ZipFile(replacement, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    replacement.replace(path)


__all__ = ["BoundImage", "resolve_images", "set_picture_properties", "annotate_workbook_images"]
