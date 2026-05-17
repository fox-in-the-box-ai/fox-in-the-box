"""Anchor-based source substitution helper for webui-side monkey-patches.

Phase-6 sibling of the agent-side `fox_overlay.agent_plugins.fox_overlay_plugin.monkey_patches._helpers`.
Logic is identical — kept duplicated to preserve clean package boundaries
between agent_plugins (entry-point loaded by hermes-agent) and
webui_patches (called from `fox_overlay.bootstrap`). A future cleanup
PR could extract to a shared `fox_overlay._substitute` module if the
duplication starts to drift.

Pattern: each monkey-patch module defines its target upstream function
and a list of ``(old, new)`` substitutions where ``old`` is an EXACT
fragment of the upstream function source. ``substitute_function`` reads
the upstream source via :func:`inspect.getsource`, applies the
substitutions sequentially, and recompiles the result in the upstream
module's namespace so it can be assigned back as the new function.

If any ``old`` anchor is missing or appears more than once, an
``AssertionError`` is raised at import time — the container fails to
boot with a precise error pointing at the upstream drift. Phase 9's
nightly upstream-watch CI catches this before users do.

Idempotency: each patch sets a per-target sentinel attribute; re-running
``apply()`` (test setup, reload, etc.) is a no-op once the sentinel is
present.
"""
import inspect
import logging
import textwrap
from types import ModuleType
from typing import Any, Dict, Optional, Sequence, Tuple

_log = logging.getLogger("fox_overlay.webui_patches")


def substitute_function(
    upstream_module: ModuleType,
    function_name: str,
    substitutions: Sequence[Tuple[str, str]],
    sentinel: str,
    extra_globals: Optional[Dict[str, Any]] = None,
) -> None:
    """Replace ``upstream_module.<function_name>`` with a patched version.

    Each ``(old, new)`` substitution is applied to the upstream source
    in sequence. Each ``old`` MUST appear exactly once or this raises
    ``AssertionError``.

    ``extra_globals`` injects additional names into the patched
    function's ``__globals__`` so the patched body can reference modules
    or symbols not imported in the upstream module (e.g., a helper
    function the Fox patch wants to call but upstream doesn't define).
    These names are scoped to the patched function only — they do not
    pollute the upstream module's namespace.

    Note: we deliberately do NOT call ``textwrap.dedent`` on the source —
    ``dedent`` normalizes whitespace-only blank lines to a bare ``\\n``,
    breaking anchors that match against the verbatim file content. For
    top-level functions there is no common leading indent to remove
    anyway. If a future caller needs to patch a class method (where the
    body is indented under the class def), it must either dedent its
    anchors itself or wrap this helper.
    """
    upstream_fn = getattr(upstream_module, function_name)
    if getattr(upstream_fn, sentinel, False):
        return

    src = inspect.getsource(upstream_fn)

    for idx, (old, new) in enumerate(substitutions):
        count = src.count(old)
        if count != 1:
            raise AssertionError(
                "[fox-overlay] monkey-patch %s.%s substitution #%d: "
                "anchor expected EXACTLY ONCE, found %dx. Upstream may have "
                "refactored this function — refresh the anchor in the "
                "fox-overlay webui_patches module. Anchor:\n%s"
                % (upstream_module.__name__, function_name, idx + 1, count, old)
            )
        src = src.replace(old, new)

    namespace = dict(upstream_module.__dict__)
    if extra_globals:
        namespace.update(extra_globals)
    code = compile(
        src,
        "<fox-overlay %s.%s>" % (upstream_module.__name__, function_name),
        "exec",
    )
    exec(code, namespace)  # noqa: S102 — namespace is the upstream module's globals

    patched_fn = namespace[function_name]
    setattr(patched_fn, sentinel, True)
    setattr(upstream_module, function_name, patched_fn)

    _log.info(
        "[fox-overlay] patched %s.%s (%d substitutions)",
        upstream_module.__name__,
        function_name,
        len(substitutions),
    )


def substitute_method(
    upstream_module: ModuleType,
    class_name: str,
    method_name: str,
    substitutions: Sequence[Tuple[str, str]],
    sentinel: str,
    extra_globals: Optional[Dict[str, Any]] = None,
) -> None:
    """Replace ``upstream_module.<class_name>.<method_name>`` with a patched version.

    Class-method counterpart to :func:`substitute_function`.
    ``inspect.getsource(SomeClass.method)`` returns the method body with
    the surrounding class indentation (4 spaces); raw substitution
    anchors must match that indentation. After all substitutions are
    applied, the source is uniformly dedented (via :func:`textwrap.dedent`)
    so :func:`compile` accepts it at module scope.

    The Phase 3 ``dedent normalizes blank lines, breaking anchors``
    warning does NOT apply here — dedent runs AFTER anchor matching is
    complete, so any whitespace normalization can't break anchors.

    The patched method is assigned to the class (not the module) via
    :func:`setattr` on ``getattr(upstream_module, class_name)``.
    Idempotency sentinel and ``extra_globals`` semantics match
    ``substitute_function``.
    """
    cls = getattr(upstream_module, class_name)
    # Read the raw descriptor (classmethod/staticmethod/function) rather
    # than the resolved attribute — the resolved attribute strips the
    # classmethod wrapper and we'd lose our sentinel after re-assignment.
    raw_descriptor = vars(cls).get(method_name)
    upstream_method = raw_descriptor if raw_descriptor is not None else getattr(cls, method_name)
    # Sentinel may live on the descriptor OR on its underlying __func__.
    if getattr(upstream_method, sentinel, False) or getattr(
        getattr(upstream_method, "__func__", upstream_method), sentinel, False
    ):
        return

    # inspect.getsource works on either the descriptor or the bound resolution.
    src = inspect.getsource(getattr(cls, method_name))

    for idx, (old, new) in enumerate(substitutions):
        count = src.count(old)
        if count != 1:
            raise AssertionError(
                "[fox-overlay] monkey-patch %s.%s.%s substitution #%d: "
                "anchor expected EXACTLY ONCE, found %dx. Upstream may have "
                "refactored this method — refresh the anchor in the "
                "fox-overlay webui_patches module. Anchor:\n%s"
                % (upstream_module.__name__, class_name, method_name, idx + 1, count, old)
            )
        src = src.replace(old, new)

    # Dedent so compile() accepts the method source at module scope.
    # Safe to dedent here — anchor matching is already complete above.
    src = textwrap.dedent(src)

    namespace = dict(upstream_module.__dict__)
    if extra_globals:
        namespace.update(extra_globals)
    code = compile(
        src,
        "<fox-overlay %s.%s.%s>" % (upstream_module.__name__, class_name, method_name),
        "exec",
    )
    exec(code, namespace)  # noqa: S102

    patched_method = namespace[method_name]
    # If the patched result is a descriptor (e.g. classmethod), set the
    # sentinel on its underlying function so the next apply() can detect
    # the already-patched state — descriptor lookup via cls.method
    # returns the underlying function, not the descriptor, so a sentinel
    # set on the descriptor alone is invisible.
    sentinel_target = getattr(patched_method, "__func__", patched_method)
    setattr(sentinel_target, sentinel, True)
    setattr(cls, method_name, patched_method)

    _log.info(
        "[fox-overlay] patched %s.%s.%s (%d substitutions)",
        upstream_module.__name__,
        class_name,
        method_name,
        len(substitutions),
    )
