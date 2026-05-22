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
