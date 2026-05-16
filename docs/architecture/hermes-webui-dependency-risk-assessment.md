# hermes-webui Dependency Risk Assessment

**Date:** 2026-05-16
**Subject:** `nesquena/hermes-webui`
**Author:** Architect 3 (Strategic Dependency Lane)
**Posture:** RECOMMEND CHANGE — see Section 9.

---

## 1. Project identity & governance

**Owner.** GitHub user `nesquena` (id 6511, account created 2008-04-11). Real name **Nathan Esquenazi**, location San Francisco, bio "Co-Founder @ CodePath.org". Linked GitHub orgs: `railsbridge`, `padrino`, `beanstalkd`, `codepath`. **No org membership in `NousResearch`.** This is an individual developer's personal project.

**Personal vs institutional.** Owner is a User account, not an Organization. Repo is published on a personal namespace. There is no parent company, foundation, or sponsoring organization on the GitHub side. The companion website `get-hermes.ai` does not advertise a corporate sponsor.

**License.** MIT, copyright "Hermes Web UI Contributors" (2025). MIT permits commercial use, modification, distribution, sublicense — Fox's bundling and redistribution are unambiguously allowed and require only attribution.

**Public roadmap / RFCs.** A `ROADMAP.md` exists and is detailed (sprint history with test counts per sprint, currently up to v0.51.x), but it is a *retrospective* changelog, not a forward-looking RFC process. There is no RFC repository, no design-doc workflow, no public issue triage policy.

**CLA / CoC / SECURITY.md.** **None.** `CONTRIBUTING.md` is one paragraph: "Thanks for contributing. … If your PR touches security-sensitive behavior, say so explicitly." No CODE_OF_CONDUCT.md. No SECURITY.md. No vulnerability disclosure address. No 2-factor enforcement signal. This means a CVE landed today would be reported in public Issues, not via coordinated disclosure.

**Relationship to NousResearch / hermes-agent.**
- Marketing relationship: README points users to `https://hermes-agent.nousresearch.com/`. The official hermes-webui homepage `get-hermes.ai` self-describes in its OG metadata as "Hermes — Community Web UI **(unofficial)**", with `og:url` of `nesquena.github.io/hermes-webui/`.
- Technical relationship: hermes-webui imports hermes-agent Python modules via `sys.path` (filesystem dependency, not PyPI). README claims dynamic feature parity.
- Reverse relationship: NousResearch's `hermes-agent` README contains **zero references to hermes-webui or nesquena**. The agent project does not acknowledge the WebUI as official.
- Cross-reference traffic: 218 hermes-agent issues mention "nesquena" or "hermes-webui," but these are user-filed cross-refs, not project-level coordination.

**Net governance assessment:** unincorporated personal project of a single individual, marketed as the WebUI for an institutional product (NousResearch's hermes-agent) **without that institution's endorsement**. Branding is "community/unofficial" by the project's own admission.

---

## 2. Maintainer health & bus factor

**Project age.** First commit on master 2026-04-22; first commit anywhere (any branch) 2026-03-30. Total git history: **47 days**.

**Top contributors (entire 47-day project history, `git shortlog -sn upstream/master`):**

| Rank | Author | Commits | % of 1,723 |
|------|--------|---------|-----------|
| 1 | nesquena-hermes | 573 | 33.3% |
| 2 | Hermes Agent (bot) | 231 | 13.4% |
| 3 | Frank Song | 155 | 9.0% |
| 4 | Michael Lam | 127 | 7.4% |
| 5 | Hermes Bot (bot) | 95 | 5.5% |
| 6 | "test" | 78 | 4.5% |
| 7 | bergeouss | 57 | 3.3% |
| 8 | ai-ag2026 | 45 | 2.6% |
| 9 | Nathan Esquenazi | 44 | 2.6% |
| 10 | dobby-d-elf | 38 | 2.2% |
| ... | (79 more contributors) | | |

**Lead maintainer share.** `nesquena-hermes` + `nesquena` + `Nathan Esquenazi` = **618 commits = 35.9% of all commits**. Add the bots `nesquena` operates (Hermes Agent + Hermes Bot + Hermes Release Agent = 328) and the maintainer-controlled commits are **946 / 1,723 = 54.9%** of upstream.

**On the GitHub contributors API** (which counts across all branches): nesquena-hermes 800 + nesquena 273 = 1,073 — same conclusion, just larger denominator.

**Bot identity.** "Hermes Agent" and "Hermes Bot" emit messages such as `Hermes Agent Stage 367: PR #2367 — fix: …` and `Hermes Agent stage-367: stamp CHANGELOG v0.51.74`. They are **the maintainer's own automation**: a release bot that batches merged PRs into "stage" branches, stamps the changelog, and cuts a tag. Email domain `agent@nesquena-hermes.local` and `hermes-bot@get-hermes.ai` confirm both are operated by nesquena. They are not third-party Dependabot equivalents.

**Real human throughput.** Subtracting nesquena and his bots, the top non-maintainer contributors in 47 days:

- Frank Song (155) — appears as core team
- Michael Lam (127)
- "test" (78) — likely test fixture commits, not human authorship
- bergeouss (57)
- ai-ag2026 (45) — ambiguous identity
- dobby-d-elf (38), starship-s (33), Dennis Soong (27), Jordan SkyLF (25), fxd-jason (18)

**Drive-by ratio.** 89 distinct contributors total. The long tail (rank 25-89) shows 65 contributors with ≤6 commits each. This is healthy drive-by traffic (a typical OSS distribution) but not an institution-scale contributor pool.

**PR throughput vs. authorship.** 1,649 total PRs in 47 days = 35 PRs/day opened. 963 merged + 657 closed-unmerged + 22 open = 59% merge rate. Oldest open PR is 15 days old (#1418, opened 2026-05-01). PR triage is fast, but the merge filter is aggressive.

**Maintainer absences.** **Zero.** nesquena has authored commits on **48 distinct days out of the 48-day project history.** Longest gap: 0 days. The project has not yet had a single weekend without maintainer activity. This is also a *symptom*: the project is too young to have demonstrated resilience to a maintainer absence.

**Single point of failure.** If `nesquena` stops tomorrow:
- Release bot stops cutting tags (it's operated from his machine — emails `@nesquena-hermes.local`).
- Stage-batch merging stops (it's the bot's job).
- The "official" upstream remote on GitHub remains owned by him personally — no org continuity plan exists.
- Frank Song (#3) and Michael Lam (#4) combined are 282 commits; they could plausibly fork-and-continue, but neither has demonstrated release-management capability or owns the `get-hermes.ai` domain.
- Bus factor: **1**.

---

## 3. Shipping velocity & quality signals

**Commit cadence (all on master, last few days):** 2026-05-13: 130, 05-14: 77, 05-15: 100, 05-16 (partial): 33. Last 7 days: 660 commits = **94 commits/day**. Last 14 days: 1,328 = 95/day. The "60 commits/day" figure in the prior research underestimates current cadence by ~50%.

**Tag cadence.** 421 git tags in 47 days = **8.96 tags/day**. 397 GitHub releases (~24 tags are not promoted to releases). Tag scheme is strict semver: `v0.51.74`, `v0.51.73`, etc. — every accepted stage-batch becomes a tag. Effectively, **tags are merge-commit markers, not stability signals**.

**Major / minor / patch breakdown.** Project is on the v0.51.x series after 47 days of life — the minor number has incremented ~50 times. No v1.0 yet. The v0.x → v0.x+1 boundary appears to mean "started a new sprint," not "API broke." This makes semver effectively useless as a stability oracle for downstream pinning.

**Revert / yank history.** No tags match `revert|yank|rollback|hotfix|patch`. 5 commits contain "revert" in the subject line, including:
- `stage-362: revert #2323 — Opus caught silent regression in profile routing`
- `Revert "Merge pull request #2323 into stage-362"`
- `release: v0.50.242 — revert assistant serif font + remove Calm theme (#1299)`

This is healthy — reverts happen and are explicit. No history of yanked releases, but the project is too young (47 days) to show a long-term pattern.

**Commit type breakdown (from subject-line keywords):**
- "fix" / "bug": 622 / 1,724 = **36.1%**
- "feat" / "feature": 130 / 1,724 = **7.5%**
- "refactor" / "cleanup" / "chore": 95 / 1,724 = **5.5%**
- Remaining ~50% are stage merges, test commits, locale/i18n commits, and CHANGELOG stamps.

The fix:feat ratio of ~5:1 is high. Interpretation: either a mature stabilization sprint, or a high churn/regression rate. Given the 95-commit/day cadence and the volume of "Opus-caught" advisory commits (e.g., "stage-364: Opus-caught live SSE event_id fix (side-channel approach)"), the more likely read is **lots of regressions caught fast** — high agility but elevated regression risk per merge.

**Test count over time.** ROADMAP.md tracks test counts per sprint. Sprint 23: 424 tests. Sprint 34 (v0.50.0): 742 tests. Currently: 313 test files (rough count) representing ~3,936 tests collected per the v0.50.278 ROADMAP entry. Test count grows every sprint — positive maturity signal.

**Open / closed issue ratio.** 79 open / 640 closed = **11.0% open**. Healthy for an active project. Oldest open issue: #195 (37 days old, "Reliability: os.environ race condition between concurrent agent sessions"). A meaningful reliability bug has sat 37 days without a fix.

**Stale PR rate.** 22 open / 1,649 total = 1.3% open. Oldest open PR is 15 days old. **Triage is excellent.**

---

## 4. Alignment with hermes-agent

**Coupling model.** WebUI imports hermes-agent modules via `sys.path` injection at startup. There is no version pin, no requirements.txt entry — webui adapts to whatever agent it finds on disk.

**Release coupling.** hermes-agent's latest release is `v2026.5.7` (date-stamped, 2026-05-07, internal version `v0.13.0`). hermes-webui's latest is `v0.51.74` (2026-05-16). The two projects are **on completely independent versioning schemes** with no coordinated release notes.

**Lag time when agent changes APIs.** Cannot be measured precisely from git logs alone, but the absence of any version pin and the in-tree references to "WebUI run state consistency contract" (e.g., PR #2363, "Document WebUI run state consistency contract") suggest **the contract is being discovered and documented in-flight**, not designed up-front. There is risk that an agent change ships and webui is silently broken until someone notices.

**Does WebUI surface new agent hooks promptly?** PR titles like "feat(mcp): Option A rewrite — import api.models/api.profiles canonically" and "Stage 323: PR #1895 — MCP Option A rewrite" suggest webui follows agent's MCP changes within days. Cadence is fast on the surface; quality is unknown.

**Does webui ever lead the agent?** No evidence in git logs of webui shipping UI for unreleased agent features. The directionality is consistently agent-first, webui-follows.

**Operational implication.** If Fox bumps hermes-agent independently, it can desync webui without warning. Fox's CI must test the *pair* end-to-end at every bump.

---

## 5. Alignment with Fox's needs

**Fox's modification footprint** (from the upstream-separation-plan, file-level audit):
- 22 NEW files (Tailscale, local fallback, Ollama URL, hostname, onboarding wizard, Fox visual shell, etc.)
- 29 MODIFIED files (api/routes.py +1510/-98; static/panels.js +1181/-7; static/index.html +174/-31)
- 7 DELETED files (upstream onboarding entirely)
- "Always-conflict" set: `api/routes.py`, `api/onboarding.py`, `api/streaming.py`, `api/config.py`, `static/index.html`, `static/panels.js`

**Recent upstream features Fox wants vs. doesn't:**

Recent (last 30 days) upstream features identifiable from changelog/commit subjects:
- Kanban v1 launch (Sprint 329, multiple commits, modal/i18n/profile-cache/dispatcher work) — **ambiguous for Fox**: Fox audience is non-technical; kanban as task tracker may or may not surface in onboarding.
- Compression / context-window indicators (live usage ring, compression reference cards) — **wanted**.
- WebUI run event journal replay (PR #2283) — **probably wanted** (resilience feature).
- i18n locale parity (DE, multiple zh-Hant fixes, settings sidebar i18n) — **neutral / mildly wanted** for global rollout.
- MCP server "Option A rewrite" — **wanted** (Fox audience wants MCP).
- Markdown table cell paragraph spacing fixes — **neutral**.
- Skills sidebar management (#268), real-time bidirectional sync between Gateway sessions (#272) — **wanted**.
- WebUI extension hooks (`api/extensions.py`, added 2026-05-01) — **directly relevant** to Fox's overlay strategy.

**Collisions with Fox-specific work:**
- Onboarding: Fox replaced upstream's onboarding entirely (deletes 689 LOC net, deletes 6 upstream onboarding tests). Every upstream onboarding change is a guaranteed conflict.
- Local-fallback: Fox added 616 LOC for Ollama-fallback orchestration. If upstream ever ships a similar feature, the duplication will be painful.
- Tailscale (877 LOC): pure Fox surface. No upstream equivalent. Safe.
- Hostname (279 LOC): pure Fox. Safe.
- Custom Ollama URL (#109): Fox-added. Upstream may add this themselves under a different env-var name and conflict.

**Extensibility surface upstream provides.**
- `api/extensions.py` (added 2026-05-01, 14 days old): script-injection + sandboxed-static extension hooks via env vars `HERMES_WEBUI_EXTENSION_DIR`, `HERMES_WEBUI_EXTENSION_SCRIPT_URLS`, `HERMES_WEBUI_EXTENSION_STYLESHEET_URLS`. Cap of 32 URLs per env var. **This is a brand-new surface Fox should evaluate, but it covers static-asset overlays and JS injection only — it cannot cover Python route additions or onboarding rewrites.** Fox's 22 new Python files cannot live here.
- `HERMES_WEBUI_AGENT_DIR` env var: hermes-agent path discovery. Fox uses.
- `SKIP_ONBOARDING` env var: skip upstream wizard. Fox uses.
- `HERMES_WEBUI_EXTENSION_*`: script/style injection. Fox does NOT yet use; could replace some of `static/fox-in-the-box.{css,js}` overlay.

**Verdict on extensibility.** Upstream's extension surface is intentionally narrow ("self-hosted extension surface: configured same-origin script/style injection plus sandboxed static file serving"). It is sufficient for branding overlays, **insufficient for Fox's Python additions**. Fox's overlay needs will not be served by upstream's extension model alone.

---

## 6. Stability & restructure risk

**Large-scale rewrites observed.** From ROADMAP.md Sprint history:
- Sprint 5: `server.py` 1778→1042 lines (JS extraction)
- Sprint 9: "app.js deleted and replaced by 6 modules"
- Sprint 10: "server.py split into api/ modules"
- Sprint 11: "routes extracted to api/routes.py (server.py 704→76 lines)"
- Sprint 23/34/40: rendering rewrites (renderMd hardening, autolink ordering, _ob_stash)
- "v0.50.0 UI overhaul (Sprint 34)": composer-centric controls, workspace state machine
- "MCP server Option A rewrite" (Sprint 322-323)
- "Three-column layout with left rail + main-view migration" (#899)

**Frequency:** roughly one structural change per sprint (1-2 weeks). For a 47-day-old project, that is **continuous architectural churn**, not a stable foundation.

**API stability.** Two examples of removal-without-deprecation in the recent log:
- "fix: remove deprecated btnCancel; localise composer tooltips with disabled reason branching"
- "chore: remove deprecated DeepSeek V3/R1 models, keep only V4"

Pattern: things get deprecated and removed within the same sprint cycle. There is no observable LTS / deprecation-window discipline.

**Database schema changes.** Recent commits include:
- "fix(auth): HMAC length migration bridge and restore Secure cookie heuristic" (32→64 char HMAC migration)
- "fix(recovery): preserve worktree metadata + workspace + message_count on state.db sidecar rebuild"
- "fix(recovery): close concurrency hazards in state.db sidecar reconciliation"

The SQLite `state.db` has had at least one schema migration with a "bridge" — meaning upstream is willing to break backward compat as long as a one-shot bridge exists. Fox's snapshots/backups must be tested across these.

**In-flight rewrites visible in branches.** Active upstream branches: `master`, `gh-pages`, `docs/contributors-v0.51.58-refresh`, `fix-2083-title-retry`, `fix/2177-nvidia-prefix-strip`, and `stage-363` through `stage-367`. The "stage-N" branches are the release-batch staging branches — not long-lived feature branches. **No evidence of an in-flight large-scale rewrite (no `react-rewrite/`, `vue-port/`, etc.).** This is a positive: nothing major is hidden in branches waiting to land.

---

## 7. Three options compared

| Dimension | Stay + separate (12d plan) | Stay + minimal patch | Fork-and-stop | Replace (build) |
|---|---|---|---|---|
| **Up-front cost** | 12 eng-days | 2-3 eng-days | 0 days | (out of scope — separate architect) |
| **Ongoing maintenance** | 0.5-1 day/week to rebase patch series against ~95 commits/day upstream | 1-2 days/week as drift accumulates; faster decay | Near-zero, pinned to a tag | Variable |
| **Security posture** | Strong: pull weekly, get CVE fixes | Moderate: periodic catch-up, possibly missing fixes | **Weak**: any post-pin CVE requires manual patch on a stale base | Strong (we own surface) |
| **Feature freshness** | High: ride the 95-commit/day train | Medium: take features on a delay | **Frozen** at pin date | Whatever Fox decides to ship |
| **Ability to diverge** | Medium: every Fox-only feature fights routes.py / onboarding.py / panels.js | Low: divergence amplifies conflict cost | **High**: total freedom, no merges | **Highest**: greenfield |
| **Dependency-graph simplification** | None — still couples to upstream weekly | None | Yes — eliminates upstream-tracking workflow | Yes — eliminates upstream entirely |
| **Risk if maintainer disappears** | Moderate: stage-batches stop, but Fox can pick from existing tagged release | Same as Stay+separate | **Zero** — Fox already self-sufficient | Zero |
| **Risk if NousResearch ships official WebUI** | High — upstream may pivot or get abandoned | High — same | Insulated (Fox has frozen base) | Insulated |
| **Risk if upstream relicenses or commercializes** | High (must fork at the cut) | High | **Zero** (already past the cut) | Zero |

**Note on "Replace":** I am not sizing it per brief. Reference only — it is the option a separate architect is studying.

---

## 8. "What if upstream pivots" scenarios

**Scenario A: nesquena rewrites the frontend in React.**
- *Detection:* No tripwire today. The first signal would be a feature branch like `react-rewrite/` appearing on the upstream remote, or a series of commits with `feat(react): …` subjects. Fox would notice on the next `git fetch upstream && git log upstream/master`.
- *Reaction time:* Fox's overlay (`static/fox-in-the-box.{css,js}`, all of `static/panels.js` modifications) is built against vanilla-JS DOM. A React rewrite would invalidate **100% of Fox's static/ patches** (the ~3,000+ LOC of static modifications).
- *Probability assessment:* No git evidence of this in any current branch. Risk over 6 months: low-to-moderate. Maintainer is on a feature treadmill, not a rewrite.

**Scenario B: NousResearch decides to ship their own official WebUI.**
- *Detection:* A commit landing in `NousResearch/hermes-agent` referencing a new internal `webui/` directory, or an announcement on `nousresearch.com`. No upstream cross-reference exists today.
- *Reaction time:* Fox could continue with nesquena's "community/unofficial" version indefinitely under MIT, but the marketing claim (in WebUI's own README) of "the WebUI for hermes-agent" would become untrue and a NousResearch official UI would likely be the user expectation.
- *Probability:* Materially elevated by the asymmetric relationship (webui name-drops agent; agent ignores webui). NousResearch has institutional capacity (orgs, 152K stars) to ship one in days if they want.

**Scenario C: Upstream introduces a paid tier or relicenses.**
- *Detection:* License file change on master. Easily monitored.
- *Mitigation:* MIT is irrevocable for prior versions. Fox can fork at the last MIT commit. Cost: lose all post-cut features.
- *Probability:* Personal projects rarely relicense; corporate ones do. Risk is low *unless* nesquena monetizes get-hermes.ai, in which case risk jumps.

**Scenario D: CVE drops, upstream patches, Fox is too far behind to absorb.**
- *Today's state:* Fox is 1,250 commits behind, growing by ~95/day. A critical CVE patch lands in commit X on `upstream/master`; cherry-picking X cleanly may require pulling 50-200 prerequisite commits.
- *Mitigation:* The 12-day separation plan would establish patch-series discipline that makes cherry-picks straightforward. Fork-and-stop would require Fox to write the security patch independently against a stale base.

---

## 9. Recommendation

**Recommendation: Adopt the 12-day separation plan, BUT cap further investment in upstream-tracking at 60 days. Use that window to validate whether the cadence is sustainable for Fox, and parallelize discovery on the React-replacement option (separate architect) so it is shovel-ready if the answer is no.**

This is not "stay" and not "fork-and-stop." It is "stay, instrumented, with an exit ramp."

**The reasoning, in one paragraph.** Upstream is one human, his bots, and 87 drive-by contributors, on a 47-day-old codebase, shipping 95 commits per day, on a contract with hermes-agent that is "discovered in-flight," with no governance scaffolding (no CLA, no SECURITY.md, no CoC), branded by its own homepage as "unofficial," and structurally rewritten roughly once per sprint. Fork-and-stop forfeits security patches on a project too immature to predict the CVE arrival rate of. Build-from-scratch is the obvious long-term answer but the right-now answer is to buy time at the lowest cost. The 12-day separation plan buys ~3-4 months of feature parity and CVE-tracking at ~0.5-1 day/week steady-state — that is a defensible bet **provided the bet is reviewed at day 60.**

**The single precondition that would change my answer to "fork-and-stop now":** if maintenance cost in the first 4 weeks of the separated state exceeds 1.5 days/week (i.e., upstream cadence forces more rebase work than predicted), fork-and-stop becomes correct because the separation investment did not pay back.

**The single precondition that would change my answer to "replace now":** if NousResearch announces or visibly begins work on an official hermes-webui (detection: any commit in `NousResearch/hermes-agent` referencing a `webui/` directory, or a press release), the upstream becomes a deprecating asset and Fox should pivot to the build-our-own track immediately.

---

## 10. Tripwires Fox should set up either way

These are mechanical signals that route information to Fox without depending on Fox engineers proactively reading upstream commits.

1. **Daily `git fetch upstream && git log` digest.** Cron job (GitHub Action or local) that:
   - Posts a Slack/email summary of the previous day's upstream commit subjects, grouped by author.
   - Highlights any commit mentioning `breaking|deprecat|migration|rewrite|schema|password|auth|csrf|xss|injection`.
   - Highlights any commit touching the "always-conflict" set: `api/routes.py`, `api/onboarding.py`, `api/streaming.py`, `api/config.py`, `static/index.html`, `static/panels.js`.

2. **License watch.** GitHub Action that diffs `LICENSE` between `upstream/master` and the previous fetch. Page Dennis on any change.

3. **Branch-creation watch.** Action that lists all upstream branches daily; alerts on any new branch matching `react|vue|svelte|preact|rewrite|v1|next|major`.

4. **NousResearch official-UI watch.** Daily check of `NousResearch/hermes-agent`'s tree for a `webui/` or `frontend/` or `static/` directory; alert on appearance.

5. **Maintainer absence canary.** Alert if `nesquena` has zero commits to `upstream/master` for 5 consecutive days. (Today's baseline: zero such gaps in 48 days. Any 5-day gap is a 100x deviation from baseline.)

6. **CVE feed.** Subscribe to GitHub Security Advisories for `nesquena/hermes-webui`. Subscribe to Python advisory DB for any pinned dependency in `requirements.txt`.

7. **Stage-batch monitoring.** The "Hermes Agent" bot stamps every release. If that stamp pattern (`Hermes Agent stage-NNN: stamp CHANGELOG vX.Y.Z`) breaks for >48 hours, the maintainer's release pipeline is down — early signal of a maintainer outage even if commits are still flowing from contributors.

8. **End-to-end pair test in Fox CI.** Every Fox build runs hermes-webui (current pin) against hermes-agent (current pin). Any pair-mismatch failure triggers a webui-pin freeze rather than auto-bumping.

9. **Patch-series rebase clock.** Track time-to-rebase per upstream pull. If average time-to-rebase exceeds 4 hours per pull for 3 consecutive pulls, escalate to a pin freeze and a strategic re-evaluation.

10. **Open-issue-age sentry.** Track the age of the oldest unresolved upstream issue. The current value is 37 days (#195). If that ever exceeds 90 days while the project is still <12 months old, treat it as a maintenance-bandwidth red flag.
