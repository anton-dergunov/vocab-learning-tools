from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


class UnsafeSVGError(ValueError):
    """Raised when generated SVG contains unsafe or unsupported content."""


_ALLOWED_ELEMENTS = {
    "svg",
    "g",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "title",
    "desc",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
}
_ALLOWED_ATTRIBUTES = {
    "viewBox",
    "width",
    "height",
    "x",
    "y",
    "x1",
    "y1",
    "x2",
    "y2",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "d",
    "points",
    "fill",
    "fill-opacity",
    "fill-rule",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-opacity",
    "opacity",
    "transform",
    "offset",
    "stop-color",
    "stop-opacity",
    "clip-path",
    "id",
}
_SAFE_VALUE = re.compile(r"^[#(),.%+\-\w\s]+$")
_LOCAL_URL = re.compile(r"^url\(#[A-Za-z_][\w.-]*\)$")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sanitize_svg_text(svg: str, *, max_bytes: int = 2_000_000) -> str:
    encoded = svg.encode("utf-8")
    if len(encoded) > max_bytes:
        raise UnsafeSVGError(f"SVG exceeds {max_bytes} bytes")
    if "<!DOCTYPE" in svg.upper() or "<!ENTITY" in svg.upper():
        raise UnsafeSVGError("DOCTYPE and ENTITY declarations are not allowed")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise UnsafeSVGError(f"Invalid SVG XML: {exc}") from exc
    if _local_name(root.tag) != "svg":
        raise UnsafeSVGError("SVG root element is required")

    for element in root.iter():
        name = _local_name(element.tag)
        if name not in _ALLOWED_ELEMENTS:
            raise UnsafeSVGError(f"Unsupported SVG element: {name}")
        element.tag = name
        for attribute, value in list(element.attrib.items()):
            attribute_name = _local_name(attribute)
            if attribute_name.lower().startswith("on") or attribute_name not in _ALLOWED_ATTRIBUTES:
                del element.attrib[attribute]
                continue
            value = value.strip()
            if "url(" in value.lower() and not _LOCAL_URL.fullmatch(value):
                raise UnsafeSVGError(f"External SVG reference in {attribute_name}")
            if not _SAFE_VALUE.fullmatch(value):
                raise UnsafeSVGError(f"Unsafe value for SVG attribute {attribute_name}")
            if attribute != attribute_name:
                del element.attrib[attribute]
                element.attrib[attribute_name] = value

    root.set("xmlns", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def sanitize_svg_file(source: Path, destination: Path) -> Path:
    sanitized = sanitize_svg_text(source.read_text(encoding="utf-8"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(sanitized, encoding="utf-8")
    return destination


def normalize_image(
    source: Path,
    destination: Path,
    *,
    width: int,
    height: int,
    image_format: str,
    quality: int,
    sanitized_svg_path: Path | None = None,
) -> Path:
    """Normalize raster/SVG input onto a white card-sized canvas."""
    from PIL import Image, ImageOps

    raster_source = source
    if source.suffix.lower() == ".svg":
        sanitized = sanitized_svg_path or source.with_name(f"{source.stem}.sanitized.svg")
        sanitize_svg_file(source, sanitized)
        raster_source = sanitized.with_suffix(".png")
        try:
            import cairosvg
        except ImportError:
            converter = shutil.which("rsvg-convert")
            if not converter:
                raise RuntimeError(
                    "CairoSVG or rsvg-convert is required to normalize SVG output; "
                    "install requirements/benchmark.txt"
                )
            subprocess.run(
                [
                    converter,
                    "--width",
                    str(width),
                    "--height",
                    str(height),
                    "--output",
                    str(raster_source),
                    str(sanitized),
                ],
                check=True,
                capture_output=True,
            )
        else:
            cairosvg.svg2png(
                url=str(sanitized),
                write_to=str(raster_source),
                output_width=width,
                output_height=height,
            )

    with Image.open(raster_source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width, height), "white")
        offset = ((width - image.width) // 2, (height - image.height) // 2)
        canvas.alpha_composite(image, offset)
        output = canvas.convert("RGB")
        destination.parent.mkdir(parents=True, exist_ok=True)
        save_format = "JPEG" if image_format == "jpeg" else image_format.upper()
        save_options = {"quality": quality} if save_format in {"JPEG", "WEBP"} else {}
        output.save(destination, format=save_format, **save_options)
    return destination
