#!/usr/bin/env python3
"""Regenerate Fox WebUI and Electron icons from the canonical brand SVG."""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path

import cairosvg
from PIL import Image

WEBUI_PNG_SIZES = {
    "favicon-32.png": 32,
    "favicon-192.png": 192,
    "favicon-512.png": 512,
    "apple-touch-icon.png": 180,
}
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_svg(source: Path, size: int) -> Image.Image:
    data = cairosvg.svg2png(
        bytestring=source.read_bytes(), output_width=size, output_height=size
    )
    if data is None:  # pragma: no cover - bytestring rendering always returns bytes
        raise RuntimeError("CairoSVG returned no image data")
    return Image.open(BytesIO(data)).convert("RGBA")


def generate(repo_root: Path) -> None:
    webui_dir = repo_root / "packages" / "fox-overlay" / "webui_brand"
    source = webui_dir / "favicon.svg"
    electron_dir = repo_root / "packages" / "electron" / "assets"

    canonical = source.read_bytes()
    (webui_dir / "favicon-512.svg").write_bytes(canonical)
    for filename, size in WEBUI_PNG_SIZES.items():
        render_svg(source, size).save(webui_dir / filename, format="PNG", optimize=True)

    ico_images = [render_svg(source, size) for size in ICO_SIZES]
    ico_images[-1].save(
        webui_dir / "favicon.ico",
        format="ICO",
        append_images=ico_images[:-1],
        sizes=[(size, size) for size in ICO_SIZES],
    )

    icon_1024 = render_svg(source, 1024)
    icon_1024.save(electron_dir / "icon.png", format="PNG", optimize=True)
    icon_1024.save(
        electron_dir / "icon.ico",
        format="ICO",
        sizes=[(size, size) for size in ICO_SIZES],
    )
    icon_1024.save(
        electron_dir / "icon.icns",
        format="ICNS",
        append_images=[render_svg(source, size) for size in (16, 32, 64, 128, 256, 512)],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[3]
    )
    args = parser.parse_args()
    generate(args.repo_root.resolve())


if __name__ == "__main__":
    main()
