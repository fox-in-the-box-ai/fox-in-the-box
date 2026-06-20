"""GET /skillset — active skillset manifest summary (INSTANCE_CONTRACT §4.6).

Returns the name, version, contract_version, data_sources, and
capabilities_declared from the loaded skillset manifest.  When no
skillset is loaded (standalone or v1.0 instance), returns 404.

Auth position (§4.5): behind the upstream auth gate in managed mode,
open in standalone.  Registers through normal dispatch — no
PUBLIC_PATHS expansion.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_SKILLSET_PATH = "/data/skillset.yaml"


def _load_manifest() -> dict | None:
    path = Path(os.environ.get("FOX_SKILLSET_PATH", _DEFAULT_SKILLSET_PATH))
    try:
        manifest = yaml.safe_load(path.read_text())
    except OSError:
        return None
    except yaml.YAMLError:
        logger.warning("invalid YAML in skillset manifest: %s", path)
        return None
    if not isinstance(manifest, dict) or "name" not in manifest:
        logger.warning("skillset manifest missing required 'name' field: %s", path)
        return None
    return manifest


def get_skillset() -> dict | None:
    manifest = _load_manifest()
    if manifest is None:
        return None
    data_sources = []
    raw_sources = manifest.get("data_sources", [])
    if not isinstance(raw_sources, list):
        raw_sources = []
    for src in raw_sources:
        if isinstance(src, dict) and "binding" in src:
            data_sources.append(src["binding"])
        elif isinstance(src, str):
            data_sources.append(src)
    capabilities_declared = []
    caps = manifest.get("capabilities", {})
    if isinstance(caps, dict):
        capabilities_declared = [k for k, v in caps.items() if v]
    return {
        "name": manifest.get("name", ""),
        "version": manifest.get("version", ""),
        "contract_version": manifest.get("contract_version", ""),
        "data_sources": data_sources,
        "capabilities_declared": capabilities_declared,
    }


# ── Dispatcher integration ─────────────────────────────────────────────
from fox_overlay import dispatch  # noqa: E402


def _handle_get(handler, parsed) -> bool:
    if parsed.path != "/skillset":
        return False
    from api.helpers import j
    result = get_skillset()
    if result is None:
        j(handler, {"error": "no skillset loaded"}, status=404)
    else:
        j(handler, result)
    return True


dispatch.register_get("/skillset", _handle_get, allow_bare=True)
