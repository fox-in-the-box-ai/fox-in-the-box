"""Fox additive webui modules — Phase 5 of v0.6.0 upstream-separation.

Each module here owns a `/api/...` path prefix that Fox added on top of
upstream hermes-webui. The modules import upstream's `api.helpers`
(`j`, `read_body`) and register their dispatcher entries at module-load
time. `fox_overlay.bootstrap.install()` imports this package as a
single `import fox_overlay.webui_modules`, which triggers each
sub-module's registration, then calls `dispatch.freeze()`.

Ordering: ollama lands first (smallest, fewest upstream couplings);
session_recovery lands last (longest smoke + #129 failover-engine
coupling). See `docs/architecture/v0.6.0-github-breakdown-v2.md` §item
14.
"""
from . import onboarding  # noqa: F401  -- registers /setup (bare) + /api/setup/; provides _write_env_key for hostname
from . import ollama  # noqa: F401  -- registers /api/ollama/ at import
from . import tailscale  # noqa: F401  -- registers /api/tailscale/ at import
from . import local_fallback  # noqa: F401  -- registers /api/local-fallback/ at import
from . import models_download  # noqa: F401  -- registers /api/local-models (bare) at import
from . import hostname  # noqa: F401  -- registers /api/settings/hostname (bare); imports _write_env_key from onboarding
from . import test_hooks  # noqa: F401  -- (v0.7.7 #264) registers POST /test/* ONLY when FITB_TEST_MODE=1; production builds = no-op
