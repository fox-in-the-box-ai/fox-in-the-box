# Electron One-Click Smoke Matrix

This matrix validates that desktop users can reach web onboarding in one click.

**Runtime under test:** Electron 43.4.0 (Chromium 150 / Node 24) on main since #750 — ships with the next release; v0.7.60 shipped 42.8.0. Run the full matrix on both platforms whenever the Electron major changes.

## Platforms

- Windows 11 (Docker Desktop fresh install path)
- macOS 14+ (Docker Desktop present and first launch path)

## Scenarios

1. Docker absent:
   - Launch app.
   - Allow guided Docker setup.
   - Verify browser opens `http://127.0.0.1:8787/` (native hermes-webui first-run flow — the former Fox `/setup` wizard was removed) without restarting the flow manually.
2. Docker installed but stopped:
   - Stop Docker Desktop.
   - Launch app and verify daemon wait/recovery flow, then onboarding opens.
   - **Assert no unprompted upgrade:** with an existing Docker Desktop install, the guided setup must not run `brew upgrade`/installer flows without explicit consent (#749 — design decision pending; record observed behavior).
3. Slow image pull:
   - Clear local image `ghcr.io/fox-in-the-box-ai/cloud:stable`.
   - Throttle network.
   - Verify progress remains visible and no false health timeout during pull.
4. Slow container boot:
   - Simulate slower startup (low CPU or cold machine).
   - Verify serialized health checks continue until healthy (or actionable timeout shown).
5. Existing stopped named container:
   - Leave stopped `fox-in-the-box` container present.
   - Launch app and verify container is reused/started (no name-conflict crash).
6. Terminal launch with closed stdout (#748):
   - Launch the packaged binary from a shell, then close/kill the parent shell.
   - Verify no `EPIPE` uncaught-exception dialog (currently FAILS — known issue #748; record until fixed).

## One-Click Success Assertion

- First run and subsequent run must open `http://127.0.0.1:8787/` within startup budget.
- Collect `main.log` and diagnostics text for any failure.
