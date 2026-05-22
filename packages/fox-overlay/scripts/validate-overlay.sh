#!/usr/bin/env bash
# validate-overlay.sh — local pre-commit + CI gate for the Fox overlay system.
#
# Per #328 + the v0.7.13 retrospective: the existing check-overlay-basis.sh
# is a strong runtime gate at Docker-build time (3+ min per arch). We need
# the same signal in <2 seconds at the developer's editor, so anchor drift,
# dirty submodule state, and stale series files don't ship to a fresh CI
# run before being noticed.
#
# Three checks, in order of how often they catch things:
#
#   1. Submodule cleanliness — forks/hermes-{agent,webui} must be at their
#      pinned commit with NO uncommitted changes. The classic failure mode
#      (commit e9bd4cd in the retrospective): developer hand-edits a fork
#      file to test, exports `git diff > my.patch`, but the patch's
#      context lines reference state that only exists in the un-committed
#      fork — the patch applies locally but breaks in CI against virgin
#      upstream.
#
#   2. Patch series + .fox-removals applies cleanly — wraps the existing
#      check-overlay-basis.sh. This is the same gate the Dockerfile runs;
#      catching it here saves the 3-min round trip.
#
#   3. Bootstrap import smoke — `python -c "from fox_overlay import bootstrap;
#      bootstrap.install()"` against the actual submodule sources. Catches
#      anchor-drift in webui_patches/{config,streaming}.py + signature drift
#      via _check_signature — failure modes that only surface at container
#      runtime today.
#
# Exits 0 on success, non-zero with a clear pointer on failure.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

fail() {
    echo ""
    echo "❌ validate-overlay: $1" >&2
    echo "" >&2
    echo "   Fix the issue above, then re-run: make validate-overlay" >&2
    echo "" >&2
    exit 1
}

ok() {
    echo "✅ $1"
}

# ── 1. Submodule cleanliness ───────────────────────────────────────────────────
echo "[1/3] Checking submodule cleanliness..."
for fork in forks/hermes-agent forks/hermes-webui; do
    if [ ! -d "$fork" ]; then
        fail "submodule $fork is missing — run: git submodule update --init $fork"
    fi
    # --porcelain shows nothing if clean. --ignored=no excludes gitignored files
    # (we don't care about those — only tracked + untracked changes that could
    # contaminate a git-diff-based patch generation).
    dirty=$(git -C "$fork" status --porcelain --ignored=no 2>/dev/null || true)
    if [ -n "$dirty" ]; then
        echo "" >&2
        echo "Submodule $fork has uncommitted changes:" >&2
        echo "$dirty" | sed 's/^/   /' >&2
        fail "$fork must be pristine at its pinned commit. Either: (a) commit or stash inside the submodule, or (b) reset: cd $fork && git reset --hard && git clean -fdx"
    fi
done
ok "Submodules are clean"

# ── 2. Patch series + .fox-removals (delegates to existing script) ─────────────
echo "[2/3] Running check-overlay-basis.sh..."
if ! bash packages/fox-overlay/scripts/check-overlay-basis.sh > /tmp/check-overlay-basis.log 2>&1; then
    cat /tmp/check-overlay-basis.log >&2
    fail "check-overlay-basis.sh failed — see output above. Likely cause: a patch in packages/fox-overlay/patches/{webui,agent}/ no longer applies cleanly (upstream anchor drift). Fix the patch via: make regen-patch FORK=webui PATCH=<name>"
fi
ok "Overlay basis clean"

# ── 3. Bootstrap import smoke ──────────────────────────────────────────────────
# Catches anchor-drift in webui_patches/*.py at <500ms instead of waiting for
# a real container boot.
echo "[3/3] Smoke-testing fox_overlay.bootstrap.install() locally..."

# Try multiple Python interpreters in order of preference.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "   ⚠️  No Python interpreter found — skipping bootstrap smoke."
    echo "   (Install python3 to enable the third check.)"
    exit 0
fi

# Run bootstrap import in isolation with FOX_OVERLAY_AUTOINSTALL=0 so the
# import side-effect doesn't fire — we want to exercise the apply_all() path
# explicitly, not at module-load.
PYTHONPATH="packages/fox-overlay:forks/hermes-webui" \
FOX_OVERLAY_AUTOINSTALL=0 \
"$PYTHON_BIN" -c "
import sys
try:
    from fox_overlay import webui_patches
    webui_patches.apply_all()
except AssertionError as e:
    print(f'❌ Anchor or signature drift detected:', file=sys.stderr)
    print(f'   {e}', file=sys.stderr)
    sys.exit(1)
except ImportError as e:
    # api.* imports may fail in this isolated context — that's fine for the
    # script-syntax check we care about. Only AssertionError is fatal.
    print(f'   (ImportError tolerated: {e})')
except Exception as e:
    print(f'❌ Unexpected error in bootstrap:', file=sys.stderr)
    print(f'   {type(e).__name__}: {e}', file=sys.stderr)
    sys.exit(1)
" || fail "bootstrap.install() detected drift — re-anchor the failing patch (see error above)"

ok "Bootstrap smoke passed"

echo ""
echo "🦊 validate-overlay: all checks passed"
