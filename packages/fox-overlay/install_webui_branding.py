#!/usr/bin/env python3
"""Install Fox browser branding into a checked-out Hermes WebUI tree.

The upstream files remain vendor-owned. This installer uses strict anchors so a
pin change fails at build/install time instead of silently leaving Hermes titles.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

BRAND = "Fox in the box"
ASSET_NAMES = (
    "favicon.svg",
    "favicon.ico",
    "favicon-32.png",
    "apple-touch-icon.png",
    "favicon-192.png",
    "favicon-512.png",
    "favicon-512.svg",
)

REPLACEMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "static/index.html": (
        # Default theme: light instead of dark (new visitors before any localStorage key)
        (
            "t=(localStorage.getItem('hermes-theme')||'dark').toLowerCase()",
            "t=(localStorage.getItem('hermes-theme')||'light').toLowerCase()",
        ),
        (
            "themes[t]?t:'dark'",
            "themes[t]?t:'light'",
        ),
        (
            "if(skin!=='default')document.documentElement.dataset.skin=skin;}catch(e){document.documentElement.classList.add('dark');}})()",
            "if(skin!=='default')document.documentElement.dataset.skin=skin;}catch(e){}})()",
        ),
        (
            "var t=localStorage.getItem('hermes-theme')||'dark'",
            "var t=localStorage.getItem('hermes-theme')||'light'",
        ),
        (
            'id="hermes-theme-color" content="#0D0D1A"',
            'id="hermes-theme-color" content="#FAF7F0"',
        ),
        (
            'id="settingsTheme" value="dark"',
            'id="settingsTheme" value="light"',
        ),
        ("<title>Hermes</title>", f"<title>{BRAND}</title>"),
        (
            '<meta name="apple-mobile-web-app-title" content="Hermes">',
            f'<meta name="apple-mobile-web-app-title" content="{BRAND}">',
        ),
        (
            '<link rel="apple-touch-icon" sizes="512x512" href="static/apple-touch-icon.png">',
            '<link rel="apple-touch-icon" sizes="180x180" href="static/apple-touch-icon.png">',
        ),
    ),
    "static/manifest.json": (
        ('"name": "Hermes"', f'"name": "{BRAND}"'),
        ('"short_name": "Hermes"', f'"short_name": "{BRAND}"'),
        (
            '"description": "Hermes AI Agent Web UI"',
            f'"description": "{BRAND} AI assistant Web UI"',
        ),
    ),
    "static/ui.js": (
        ("document.title=assistantDisplayName();", f"document.title='{BRAND}';"),
        (
            "document.title=sessionTitle+' \\u2014 '+assistantDisplayName();",
            f"document.title=sessionTitle+' \\u2014 {BRAND}';",
        ),
    ),
    "static/boot.js": (
        ("if(!S.session) document.title=name;", f"if(!S.session) document.title='{BRAND}';"),
    ),
    "static/panels.js": (
        (
            "const bot = typeof assistantDisplayName === 'function' ? assistantDisplayName() : '';\n"
            "    document.title = bot ? mainText + ' \\u2014 ' + bot : mainText;",
            f"document.title = mainText + ' \\u2014 {BRAND}';",
        ),
    ),
    "api/routes.py": (
        (
            "<title>{{BOT_NAME}} — {{LOGIN_TITLE}}</title>",
            f"<title>{BRAND} — {{{{LOGIN_TITLE}}}}</title>",
        ),
        ("<title>Hermes is restarting</title>", f"<title>{BRAND} is restarting</title>"),
    ),
}


def replace_once_or_verify(text: str, old: str, new: str, label: str) -> str:
    old_count = text.count(old)
    new_count = text.count(new)
    if old_count == 1 and new_count == 0:
        return text.replace(old, new, 1)
    if old_count == 0 and new_count == 1:
        return text
    raise RuntimeError(
        f"branding anchor drift in {label}: old={old_count}, branded={new_count}"
    )


def install_branding(webui_root: Path, overlay_root: Path) -> None:
    asset_source = overlay_root / "webui_brand"
    static_dir = webui_root / "static"
    if not static_dir.is_dir():
        raise RuntimeError(f"Hermes WebUI static directory missing: {static_dir}")

    for relative_path, replacements in REPLACEMENTS.items():
        path = webui_root / relative_path
        text = path.read_text(encoding="utf-8")
        for old, new in replacements:
            text = replace_once_or_verify(text, old, new, relative_path)
        path.write_text(text, encoding="utf-8")

    for name in ASSET_NAMES:
        source = asset_source / name
        if not source.is_file():
            raise RuntimeError(f"Fox branding asset missing: {source}")
        shutil.copyfile(source, static_dir / name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("webui_root", type=Path)
    parser.add_argument(
        "--overlay-root", type=Path, default=Path(__file__).resolve().parent
    )
    args = parser.parse_args()
    install_branding(args.webui_root.resolve(), args.overlay_root.resolve())


if __name__ == "__main__":
    main()
