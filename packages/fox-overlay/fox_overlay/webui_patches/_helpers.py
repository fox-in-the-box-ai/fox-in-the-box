"""Anchor-based source substitution helper — webui-side re-export shim.

The actual implementation moved to :mod:`fox_overlay._substitute` in v0.7.5
to remove the pre-existing duplication with the agent-side
``_helpers.py``. The two copies had already drifted once (webui added
``substitute_method``; agent didn't). This shim keeps existing imports
like ``from ._helpers import substitute_function`` working.

Prefer importing from :mod:`fox_overlay._substitute` directly in new code.
"""
from fox_overlay._substitute import substitute_function, substitute_method  # noqa: F401
