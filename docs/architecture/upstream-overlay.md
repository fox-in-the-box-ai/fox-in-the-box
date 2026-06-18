# Upstream Overlay Strategy

Fox wraps upstream Hermes WebUI and Hermes Agent via static patches
(`packages/fox-overlay/patches/`) applied at Docker image build time.
Some of these patches fix general-purpose bugs that affect all Hermes
users, not just Fox. This document defines when and how to push those
fixes upstream.

## Decision flow: overlay-only vs upstream PR

For every new or modified overlay patch, ask:

1. **Is this Fox-specific?** Branding, Fox UI, Fox-Docker integration,
   onboarding wizard, dispatcher hooks → **overlay-only**. Stop here.

2. **Is this a bug fix or improvement any Hermes user would benefit
   from?** Colon-split parsing, CSP fixes, provider fallback logic,
   model picker deduplication → **upstream candidate**. Continue.

3. **Does upstream already have an open issue or PR for this?**
   - Yes → link to it from the Fox PR; comment on the upstream issue
     with your fix approach. If the upstream PR is stale (>30 days no
     review), consider filing a fresh PR with a clean reproduction.
   - No → file a new upstream issue + PR. Reference it in the Fox
     overlay patch header.

4. **File the upstream PR within 2 weeks** of merging the Fox overlay
   patch. Apply the `upstream-candidate` label at merge time; the
   quarterly sweep catches any that slip past the 2-week window. The
   Fox overlay is the temporary carrier; the upstream PR is the path
   to retirement.

## Workflow

```
Fox overlay patch merged
        │
        ▼
  Fox-specific? ──yes──▶ overlay-only (no upstream action)
        │
       no
        │
        ▼
  File upstream PR within 2 weeks
        │
        ▼
  Add `upstream-candidate` label to Fox issue/PR
  Add "Upstream-PR: <url>" to the Fox PR description
        │
        ▼
  ┌─────────────────────────────────┐
  │ Monitor upstream PR (quarterly) │
  │                                 │
  │  • Merged → file Fox retirement │
  │    issue; drop overlay on next  │
  │    upstream bump                │
  │                                 │
  │  • Rejected → close upstream    │
  │    PR with reason; overlay      │
  │    stays permanent              │
  │                                 │
  │  • Stale (>90 days) → ping or   │
  │    re-file with updated context │
  └─────────────────────────────────┘
```

## Detecting upstream bugs during patch refresh

When refreshing patches for a new upstream version (`bump(upstream):`):

1. **Patch applies cleanly** → no action needed.
2. **Patch conflicts** → inspect the upstream diff:
   - If upstream changed the surrounding code but didn't fix the
     underlying bug → refresh the patch context, keep the fix.
   - If upstream independently fixed the same bug → reduce or drop the
     patch hunks that are now redundant. Document in the PR which hunks
     were retired and why.
3. **Patch becomes smaller** → check whether the remaining hunks are
   still upstream-relevant or now Fox-specific. Update the
   `upstream-candidate` label accordingly.

## Quarterly sweep

Every quarter (or every 3 upstream bumps, whichever comes first):

1. List all issues/PRs with the `upstream-candidate` label.
2. For each, check the upstream PR status:
   - Merged upstream → file retirement issue, schedule patch drop.
   - Open and active → no action.
   - Stale → ping or re-file.
   - Rejected → remove `upstream-candidate` label, document reason.
3. Review recent overlay patches for any new upstream candidates that
   were missed.

## Historical examples

**Patches 007/008 (colon-split fix):** Fox carried a 4-hunk fix for
model ID colon-split parsing bugs in `ui.js` and `routes.py`. In
upstream v0.51.421, Hermes independently fixed
`_normalizeConfiguredModelKey` — one of the four affected call sites.
Fox patch 007 was reduced from 4 hunks to 3 during the v0.51.475 bump
(the fourth site, in `routes.py`, is covered by patch 008). Four
affected call sites remain patched by Fox across the two patches and
are upstream candidates.

This validates the strategy: upstream does fix shared bugs
independently, and carrying the overlay in the interim is the correct
interim measure. The retirement workflow (detect during bump → reduce
patch → eventually drop) works as designed.

## Labels

- **`upstream-candidate`** — applied to Fox issues/PRs where the
  underlying fix is upstream-relevant and should be filed as an
  upstream PR.
