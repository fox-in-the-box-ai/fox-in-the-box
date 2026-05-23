# Fox in the Box — Smoke verification log

Per the 2026-05-22 retrospective on #331, this log exists to force a written audit trail of which release was actually smoke-tested by a human before tagging. The `release.yml` workflow may (future) refuse to publish a release whose tag doesn't have a matching entry here.

## Format

```
## vX.Y.Z — YYYY-MM-DD (initials)

- [x] Section A — Header health (URL, hostname, build version)
- [x] Section B — Onboarding wizard (renders, all 3 steps work)
- [x] Section C — Provider key save + reload survival
- [ ] Section D — Tailscale auth flow  ← skipped, no tailnet handy
- [x] Section E — Local Ollama detect + use
- (etc.)

Findings:
- (anything weird the smoke uncovered)

Action items:
- (anything to file as follow-up)
```

Skipped sections are OK as long as they're explicitly noted with reason. Empty entry = checklist not run = release tag should not have shipped.

---

## v0.7.17 — 2026-05-23 (DV — first non-bypass entry; ends 3-release streak)

The release that ends the bypass streak. Pre-tag smoke executed against the PR's built container image.

Section L row "v0.7.17 Anthropic+Gemini+Bedrock provider extras…" run results — fill in `[x]` for each item before pushing the tag:

- [ ] (a) Pulled PR-built image via `FITB_IMAGE=ghcr.io/fox-in-the-box-ai/cloud:sha-<short>` or direct `docker run`
- [ ] (b) Container ready at `http://127.0.0.1:8787`
- [ ] (c) Anthropic key saved in Settings → Providers
- [ ] (d) `anthropic/claude-haiku-3-5` chat works — response arrives, NO ImportError
- [ ] (e) Gemini chat works — response arrives, NO ImportError
- [ ] (f) (Optional) Bedrock chat works — skipped if no AWS creds
- [ ] (g) Container size sanity passed (≤current+~100MB)
- [ ] (h) Playwright `wizard-renders.spec.ts` 5 specs pass (3 redirect + 2 asset); `test-hooks-safety.spec.ts` is `describe.skip` (unskip in v0.7.18, chicken-and-egg)
- [ ] (i) Regression: OpenRouter + OpenAI + Codex + Ollama still work

Findings:
- (fill in pre-tag)

Action items:
- (fill in pre-tag)

---

## v0.7.16 — 2026-05-22 (DV — bypass entry; smoke shifted post-release)

**Bypass reason:** the v0.7.15 plan was for v0.7.16 to be the first non-bypass entry, but the Win11 VM smoke is faster against a real signed .exe (downloaded from the GitHub Release) than against a `workflow_dispatch`-built artifact. Choosing to ship first and verify the release artifact directly. If any Section L row v0.7.16 item fails, the fix lands as v0.7.17.

- **CI-side verified before tag:** all PR #335 checks green (validate, smoke amd64+arm64, electron macos+windows, build amd64+arm64, manifest merge); jest 71/71 green; node --check clean on all four edited Electron source files.
- **Manual Win11 + macOS smoke deferred:** Section L row "v0.7.16 Windows installer UX bundle" (#324 + #325 + #330) will be run against the published .exe / .dmg post-tag. Update this entry in-place with the results; if items fail, file follow-ups and queue v0.7.17.
- **Audit-trail honesty:** this is the third consecutive bypass (v0.7.14, v0.7.15, v0.7.16). The "first non-bypass" milestone slips to v0.7.17. The pattern of "always defer the smoke" is exactly what got us into the #331 mess; the v0.7.17 release MUST break the streak.

---

## v0.7.15 — 2026-05-22 (DV, infrastructure release — bypass entry)

This release ships the SMOKE_LOG gate itself + a permanent regression spec for #331. It is intentionally an infrastructure-only release with no user-visible product change.

- **Bypass reason:** the release that *adds* the SMOKE_LOG enforcement gate can't itself wait for the gate to have been pre-existing. Future product-change releases (v0.7.16+) must run an actual smoke section before tagging.
- **CI gates verified:** validate-overlay green, Playwright smoke green (now includes the deferred wizard-renders redirect-fires spec — proves patch 003 from v0.7.13 actually wired the onboarding redirect against live `:stable` = v0.7.14).
- **Action items for v0.7.16:** the Windows installer UX bundle (#324 + #325 + #330). That release MUST have a real Section H / Section L smoke gate run logged here.

---

## v0.7.14 — 2026-05-22 (DV, baseline)

First entry. Pre-v0.7.14 releases shipped without entries here because this log didn't exist — #331 (onboarding missing since v0.7.0) was the consequence of that gap. v0.7.13 hotfixed #331 itself; v0.7.14 establishes the audit trail so the next #331-class regression surfaces immediately.

- Smoke checklist gates run for v0.7.14: still N/A on the retrospective release itself (it's the *infrastructure* release that makes this log meaningful, not a user-facing change worth running 80 boxes against).
- Forward commitment: starting v0.7.15, this log must have a matching entry for every tagged release. Empty/missing entry = the smoke didn't actually run = the release shouldn't ship.

---

## How to enforce

The simplest enforcement (low effort, high signal):

1. `release.yml` greps `qa/SMOKE_LOG.md` for `^## v$NEW_TAG` and fails the publish step if no match.
2. To bypass deliberately (hotfix where smoke is impractical), the maintainer adds an empty stub entry with a `Bypass reason:` line — forces the lie in writing.

This is the v0.7.15+ work; v0.7.14 just ships the log itself.
