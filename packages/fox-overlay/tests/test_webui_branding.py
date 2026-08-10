"""Regression tests for canonical Fox favicon, PWA, and desktop branding."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path

from PIL import Image

OVERLAY_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = OVERLAY_ROOT.parents[1]
BRANDING_INSTALLER = OVERLAY_ROOT / "install_webui_branding.py"
EXPECTED_SVG_SHA256 = "e3084e2318e4e4f54973af4bd19ca68bace67262ef1edd01ee2ffbe46c610873"
ICO_SIZES = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}


def _load_installer():
    spec = importlib.util.spec_from_file_location("install_webui_branding", BRANDING_INSTALLER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_svg_hashes_match_published_brand_mark() -> None:
    for name in ("favicon.svg", "favicon-512.svg"):
        data = (OVERLAY_ROOT / "webui_brand" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == EXPECTED_SVG_SHA256


def test_webui_rasters_are_rgba_at_declared_dimensions() -> None:
    expected = {
        "favicon-32.png": (32, 32),
        "favicon-192.png": (192, 192),
        "favicon-512.png": (512, 512),
        "apple-touch-icon.png": (180, 180),
    }
    for name, dimensions in expected.items():
        with Image.open(OVERLAY_ROOT / "webui_brand" / name) as image:
            assert image.format == "PNG"
            assert image.size == dimensions
            assert image.mode == "RGBA"
            assert image.getchannel("A").getpixel((0, 0)) == 0

    with Image.open(OVERLAY_ROOT / "webui_brand" / "favicon.ico") as image:
        assert image.info["sizes"] == ICO_SIZES


def test_electron_icons_use_full_canonical_size_sets() -> None:
    assets = REPO_ROOT / "packages" / "electron" / "assets"
    with Image.open(assets / "icon.png") as image:
        assert image.size == (1024, 1024)
        assert image.mode == "RGBA"
        assert image.getchannel("A").getpixel((0, 0)) == 0
    with Image.open(assets / "icon.ico") as image:
        assert image.info["sizes"] == ICO_SIZES
    with Image.open(assets / "icon.icns") as image:
        assert image.size == (1024, 1024)
        sizes = set(image.info["sizes"])
        assert (512, 512, 2) in sizes
        assert (16, 16, 2) in sizes


def test_installer_patches_every_browser_title_path_and_preserves_refs(tmp_path: Path) -> None:
    webui = tmp_path / "hermes-webui"
    static = webui / "static"
    api = webui / "api"
    static.mkdir(parents=True)
    api.mkdir()

    (static / "index.html").write_text(
        '<title>Hermes</title>\n'
        '<base href="relative/subpath/">\n'
        '<link rel="icon" href="static/favicon.svg">\n'
        '<link rel="manifest" href="manifest.json">\n'
        '<meta name="apple-mobile-web-app-title" content="Hermes">\n'
        '<link rel="apple-touch-icon" sizes="512x512" href="static/apple-touch-icon.png">\n',
        encoding="utf-8",
    )
    manifest = {
        "name": "Hermes",
        "short_name": "Hermes",
        "description": "Hermes AI Agent Web UI",
        "start_url": "./?source=pwa",
        "icons": [{"src": "static/favicon.svg"}, {"src": "static/favicon-512.png"}],
    }
    (static / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (static / "ui.js").write_text(
        "document.title=assistantDisplayName();\n"
        "document.title=sessionTitle+' \\u2014 '+assistantDisplayName();\n",
        encoding="utf-8",
    )
    (static / "boot.js").write_text(
        "if(!S.session) document.title=name;\nsidebar.textContent=name;\n", encoding="utf-8"
    )
    (static / "panels.js").write_text(
        "const bot = typeof assistantDisplayName === 'function' ? assistantDisplayName() : '';\n"
        "    document.title = bot ? mainText + ' \\u2014 ' + bot : mainText;\n",
        encoding="utf-8",
    )
    (api / "routes.py").write_text(
        "<title>{{BOT_NAME}} — {{LOGIN_TITLE}}</title>\n"
        "<title>Hermes is restarting</title>\n",
        encoding="utf-8",
    )

    installer = _load_installer()
    installer.install_branding(webui, OVERLAY_ROOT)
    installer.install_branding(webui, OVERLAY_ROOT)  # installation is idempotent

    index = (static / "index.html").read_text(encoding="utf-8")
    assert "<title>Fox in the box</title>" in index
    assert 'content="Fox in the box"' in index
    assert 'sizes="180x180"' in index
    assert 'href="static/favicon.svg"' in index
    assert 'href="manifest.json"' in index

    installed_manifest = json.loads((static / "manifest.json").read_text(encoding="utf-8"))
    assert installed_manifest["name"] == "Fox in the box"
    assert installed_manifest["short_name"] == "Fox in the box"
    assert installed_manifest["description"] == "Fox in the box AI assistant Web UI"
    assert installed_manifest["start_url"] == "./?source=pwa"
    assert installed_manifest["icons"] == manifest["icons"]

    assert "document.title='Fox in the box';" in (static / "ui.js").read_text()
    assert "sessionTitle+' \\u2014 Fox in the box'" in (static / "ui.js").read_text()
    assert "document.title='Fox in the box';" in (static / "boot.js").read_text()
    assert "mainText + ' \\u2014 Fox in the box'" in (static / "panels.js").read_text()
    routes = (api / "routes.py").read_text()
    assert "<title>Fox in the box — {{LOGIN_TITLE}}</title>" in routes
    assert "<title>Fox in the box is restarting</title>" in routes
    assert "sidebar.textContent=name" in (static / "boot.js").read_text()

    for name in installer.ASSET_NAMES:
        assert (static / name).read_bytes() == (OVERLAY_ROOT / "webui_brand" / name).read_bytes()


def test_disabled_webui_overlay_skips_branding_installer() -> None:
    install_core = (REPO_ROOT / "packages" / "install-core" / "install-core.sh").read_text()
    match = re.search(r"(?ms)^_install_webui_branding\(\) \{.*?^\}", install_core)
    assert match, "branding function missing from install-core.sh"
    probe = (
        "set -e\n"
        "_log(){ printf '%s\\n' \"$*\"; }\n"
        "python3(){ return 99; }\n"
        f"{match.group(0)}\n"
        "FITB_DISABLE_WEBUI_OVERLAY=1\n"
        "_install_webui_branding\n"
    )
    result = subprocess.run(["bash", "-c", probe], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "Skipping WebUI branding (overlay disabled)" in result.stdout
