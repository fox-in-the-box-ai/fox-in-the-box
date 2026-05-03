# Electron One-Click Smoke Matrix

This matrix validates that desktop users can reach web onboarding in one click.

## Platforms

- Windows 11 (Docker Desktop fresh install path)
- macOS 14+ (Docker Desktop present and first launch path)

## Scenarios

1. Docker absent:
   - Launch app.
   - Allow guided Docker setup.
   - Verify browser opens `http://127.0.0.1:8787/setup` (Fox setup wizard) without restarting the flow manually.
2. Docker installed but stopped:
   - Stop Docker Desktop.
   - Launch app and verify daemon wait/recovery flow, then onboarding opens.
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

## One-Click Success Assertion

- First run and subsequent run must open the Fox setup URL `http://127.0.0.1:8787/setup` within startup budget.
- Collect `main.log` and diagnostics text for any failure.
