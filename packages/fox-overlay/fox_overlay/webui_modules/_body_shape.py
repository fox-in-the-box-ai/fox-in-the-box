"""Shared overlay helper: enforce that a POST body is a JSON object (#901).

Upstream ``api.helpers.read_body`` advertises ``-> dict`` but does not enforce
it: a valid-JSON-but-non-object body (list / bare string / number / bool /
null) parses cleanly and is returned verbatim, so every overlay handler that
trusts the annotation and dereferences with ``.get(...)`` crashes with an
``AttributeError`` → HTTP 500 + traceback.

The guard belongs here in the Fox overlay layer, NOT in upstream
``read_body`` (vendored, shared by ~10 upstream callers, a merge-conflict
anchor on the next pin bump). Every overlay POST handler routes its body read
through ``require_object_body`` so a non-object body yields a uniform,
explicit 400 instead of a 500.
"""


def require_object_body(handler):
    """Read a POST body and enforce it is a JSON object.

    Returns the parsed ``dict`` on success. On a valid-JSON-but-non-object
    body (list / str / number / bool / null) writes a clean 400 and returns
    ``None``; the caller must ``return True`` when it gets ``None`` (the
    response has already been written).
    """
    from api.helpers import bad, read_body

    body = read_body(handler)
    if not isinstance(body, dict):
        bad(handler, "Request body must be a JSON object", 400)
        return None
    return body
