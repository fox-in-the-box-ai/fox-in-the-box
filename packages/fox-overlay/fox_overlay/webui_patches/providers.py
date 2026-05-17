"""Fox webui patch: gateway hot-reload after set_provider_key.

Restores the two Fox edits to ``api/providers.py`` that were reverted
to upstream merge-base in fork PR fox-in-the-box-ai/hermes-webui#25
(Phase 6 fork-side revert).

## What Fox needs

When the user updates an API key via Settings → Providers, the gateway
process must pick up the new key. Several runtime_provider paths read
keys via ``os.getenv`` directly (OpenRouter, OpenAI), so
``invalidate_models_cache()`` alone — which only refreshes the model
dropdown — isn't enough; the gateway's process env must be refreshed.

Fox's approach: shell out to ``supervisorctl restart hermes-gateway``
after each key change. Best-effort — silently a no-op when
``supervisorctl`` is unavailable (upstream Hermes / dev environments
without supervisord).

## How the patch works

* Adds one line to ``set_provider_key`` — a call to
  ``_reload_provider_runtime()`` immediately after the existing
  ``invalidate_models_cache()`` call.
* Injects ``_reload_provider_runtime`` into the patched function's
  globals via ``extra_globals``. The helper is defined in THIS module
  so the upstream namespace stays virgin.

The original Fox patch added the helper as a module-level function in
``api/providers.py`` (so other code could call it). No other code DOES
call it — verified by grepping the fork. Defining it in the patch
namespace is therefore behaviorally equivalent and keeps the upstream
namespace untouched.
"""
import logging
import shutil
import subprocess

from ._helpers import substitute_function

_log = logging.getLogger("fox_overlay.webui_patches.providers")
_SENTINEL = "_fox_patched_set_provider_key"


def _reload_provider_runtime() -> None:
    """Best-effort restart of the gateway so new env keys take effect.

    Skipped silently outside FITB-style supervisor deployments.
    """
    if not shutil.which("supervisorctl"):
        return
    try:
        subprocess.run(
            ["supervisorctl", "-c", "/etc/supervisor/supervisord.conf",
             "restart", "hermes-gateway"],
            capture_output=True, timeout=10, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        _log.warning("Gateway hot-reload failed: %s", exc)


def apply() -> None:
    """Patch api.providers.set_provider_key to call _reload_provider_runtime."""
    from api import providers as _u

    substitute_function(
        upstream_module=_u,
        function_name="set_provider_key",
        substitutions=[
            (
                # Anchor: the existing invalidate_models_cache() call.
                # Unique within set_provider_key per upstream merge-base 9e31a2a.
                "    invalidate_models_cache()\n\n    return {",
                # Insert the hot-reload call between cache invalidation and the
                # return. Keeps Fox's pre-Phase-6 behavior identical — the
                # original Fox edit added the same call in the same position.
                "    invalidate_models_cache()\n\n"
                "    # Fox: hot-reload the gateway so the new key takes effect\n"
                "    # without a manual container restart. See\n"
                "    # fox_overlay.webui_patches.providers for rationale.\n"
                "    _reload_provider_runtime()\n\n"
                "    return {",
            ),
        ],
        sentinel=_SENTINEL,
        extra_globals={"_reload_provider_runtime": _reload_provider_runtime},
    )
