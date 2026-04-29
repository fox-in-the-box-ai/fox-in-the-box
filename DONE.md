# Task 05a — Onboarding wizard tests (DONE)

## Deliverable

- Single authoritative file: `forks/hermes-webui/tests/test_setup_api.py`
- All **12** required tests are present, with the exact names from the task spec and a **docstring** on each test function.

**Note:** An outdated path `tests/integration/test_setup_api.py` may remain as a one-line redirect docstring stub if deletion was blocked in-agent — **Supervisor should remove it** (`git rm tests/integration/test_setup_api.py`) so only the Hermes fork copy remains.

## Pytest

From repo root:

```bash
cd forks/hermes-webui && python3 -m pytest tests/test_setup_api.py -v 2>&1
```

Run was not executed in this environment; expected before Task **05b**:

- With **`forks/hermes-webui`** missing or **without importable ``server.Handler``**, collection may **error** at the `Handler_cls` fixture (`pytest.fail` with import message).
- With WebUI checked out but **routes not implemented**, tests should **fail** on assertions (wrong status codes, bodies, missing files).
- **Expected before 05b:** no syntax/import failures in the **test module itself** once `pytest` is installed under the same interpreter as Hermes dependencies.

### Cross-thread logging (API key leakage)

`pytest`’s **`caplog`** does not reliably capture logs emitted by the threaded **`HTTPServer`** worker. OpenRouter-related tests attach a **`logging.Handler`** (**`LogCapture`**) on the **root logger** and assert substring absence on `"\n".join(log_capture.records)` so key material is actually checked across threads.

## Assumptions about the web stack

- **`forks/hermes-webui/server.py`** exposes **`Handler`** (subclasses **`BaseHTTPRequestHandler`**).
- Behaviour honours **`ONBOARDING_PATH`**, **`HERMES_ENV_PATH`**, optional **`check_auth`** bypass as before.
- Tailscale **`subprocess.Popen`** patch target is **`subprocess.Popen`** (global patch as in task examples).

## Supervisor / 05b follow-ups

- Remove **`tests/integration/test_setup_api.py`** if present (move completed).
- If Tailscale implementation uses **`Popen`** only under the **`server`** module’s **`subprocess`** reference, patches may need **`@patch("server.subprocess.Popen")`** instead of patching **`subprocess.Popen`** globally.
