# Task 05a: Onboarding Wizard — Tests Only

| Field          | Value                                                                |
|----------------|----------------------------------------------------------------------|
| **Status**     | Ready                                                                |
| **Executor**   | AI agent                                                             |
| **Depends on** | Task 02 (monorepo scaffold), Task 03 (Dockerfile + container build)  |
| **Blocks**     | Task 05b — supervisor must approve tests before implementation begins |
| **Reviewed by**| Supervisor (Hermes) before 05b is handed to any agent               |

---

## Purpose

This task writes **only the tests** for the onboarding wizard backend.
No implementation code. No HTML. No CSS.

The goal is to define exactly what "done" means for task 05b before any
implementation code exists. The supervisor reviews and approves these tests
first — only then does task 05b begin.

This matters for task 05 specifically because the onboarding wizard has the
most complex state machine in the project: the redirect middleware, the
Tailscale polling loop, the step transitions, and the idempotency edge cases.
Getting the test contract right up front prevents an agent from writing
tests that validate implementation details rather than behaviour.

---

## What to Produce

One file: `forks/hermes-webui/tests/test_setup_api.py`

No other files. Do not touch `server.py`, do not create HTML or CSS files.

---

## Constraints

- Use `pytest` and the framework's test client (inspect `forks/hermes-webui/`
  to determine the framework — Flask `app.test_client()`, FastAPI `TestClient`,
  etc.)
- All subprocess calls (`tailscale login`, `supervisorctl`) must be mocked with
  `unittest.mock.patch` — tests must run with no Docker, no Tailscale, no
  supervisord present
- Tests must be runnable from the repo root with:
  ```bash
  cd forks/hermes-webui && pytest tests/test_setup_api.py -v
  ```
- Tests must **fail** when run against the unmodified upstream webui
  (i.e., they test for behaviour that doesn't exist yet). A test that passes
  before implementation is written wrong.
- All 12 required test cases must be present (see below)
- Each test must have a docstring explaining what behaviour it asserts

---

## Required Test Cases

### Redirect middleware (4 tests)

| Test name | Behaviour asserted |
|-----------|-------------------|
| `test_redirect_when_onboarding_json_missing` | `GET /` with no `onboarding.json` on disk → HTTP 302 to `/setup` |
| `test_redirect_when_completed_false` | `GET /` with `{"completed": false}` → HTTP 302 to `/setup` |
| `test_no_redirect_when_completed_true` | `GET /` with `{"completed": true}` → HTTP 200 (passes through) |
| `test_setup_and_api_routes_exempt_from_redirect` | `GET /setup` and `POST /api/setup/openrouter` with `completed=false` → NOT redirected (200 / 400, not 302) |

**Fixture pattern** — the tests must patch filesystem reads, not rely on real files:
```python
@pytest.fixture
def onboarding_incomplete(tmp_path, monkeypatch):
    cfg = tmp_path / "onboarding.json"
    cfg.write_text('{"completed": false}')
    monkeypatch.setenv("ONBOARDING_PATH", str(cfg))
    # or patch the module-level constant directly
```

---

### OpenRouter key endpoint (4 tests)

| Test name | Behaviour asserted |
|-----------|-------------------|
| `test_openrouter_valid_key_returns_ok` | `POST /api/setup/openrouter {"key": "sk-valid"}` → 200 `{"ok": true}` |
| `test_openrouter_valid_key_writes_env_file` | After valid POST, `hermes.env` contains `OPENROUTER_API_KEY=sk-valid` |
| `test_openrouter_invalid_key_no_sk_prefix` | `POST {"key": "notvalid"}` → 400 `{"ok": false, "error": "..."}` |
| `test_openrouter_empty_key` | `POST {"key": ""}` → 400 `{"ok": false, "error": "..."}` |

**File write test pattern:**
```python
def test_openrouter_valid_key_writes_env_file(client, tmp_path, monkeypatch):
    env_path = tmp_path / "hermes.env"
    monkeypatch.setenv("HERMES_ENV_PATH", str(env_path))
    client.post("/api/setup/openrouter", json={"key": "sk-test-key"})
    content = env_path.read_text()
    assert "OPENROUTER_API_KEY=sk-test-key" in content
```

The key must **not** appear in any log output. Add an assertion:
```python
    assert "sk-test-key" not in caplog.text  # use pytest caplog fixture
```

---

### Tailscale endpoints (4 tests)

| Test name | Behaviour asserted |
|-----------|-------------------|
| `test_tailscale_start_returns_ok` | `POST /api/setup/tailscale/start` → 200 `{"ok": true}`, subprocess spawned (mocked) |
| `test_tailscale_status_initial_is_waiting` | `GET /api/setup/tailscale/status` before any start → `{"status": "waiting", ...}` |
| `test_tailscale_start_idempotent` | Second `POST /api/setup/tailscale/start` while process running → 200, no second subprocess spawned |
| `test_tailscale_complete_writes_json` | `POST /api/setup/complete {"tailscale_connected": true}` → `onboarding.json` written with `completed: true` and `tailscale_connected: true` |

**Subprocess mock pattern:**
```python
@patch("subprocess.Popen")
def test_tailscale_start_returns_ok(mock_popen, client):
    mock_popen.return_value.stdout = iter([])
    response = client.post("/api/setup/tailscale/start")
    assert response.status_code == 200
    assert response.json["ok"] is True
    mock_popen.assert_called_once()
```

---

## What the Supervisor Checks

Before approving these tests and unblocking 05b, the supervisor will verify:

- [ ] All 12 test cases are present and named correctly
- [ ] Every test has a docstring
- [ ] All tests **fail** against unmodified upstream webui (run them to confirm)
- [ ] Subprocess calls are mocked — no real Tailscale or supervisorctl invoked
- [ ] API key never appears in logs (caplog assertion present)
- [ ] File writes use `tmp_path` or `monkeypatch` — no writes to real `/data`
- [ ] `pytest tests/test_setup_api.py -v` runs without import errors
  (even though all tests fail — they must at least be syntactically valid)

---

## Handoff

When done, write `DONE.md` in the worktree root containing:
- Confirmation that all 12 tests are present
- Output of `pytest tests/test_setup_api.py -v` (expected: all FAIL or ERROR, not import errors)
- Any assumptions made about the web framework (which one is in use)
- Any test cases you found impossible to write without knowing the implementation — list them
