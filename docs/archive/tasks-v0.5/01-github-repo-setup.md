# Task 01 — GitHub Repository Setup

## Summary

Create the GitHub organization and repositories needed for the Fox in the Box monorepo. This involves creating the `fox-in-the-box-ai` GitHub org, initializing the fresh `fox-in-the-box` monorepo, and forking two upstream repositories (`NousResearch/hermes-agent` and the hermes-webui upstream) into the org. No code is written in this task — it is purely GitHub account-level setup. All downstream tasks (02–05) are blocked until this task is complete.

---

## Who Does This

**Stan (human)** — GitHub org creation and repository forking require an authenticated GitHub account with org creation privileges. This task cannot be automated by an AI agent.

---

## Prerequisites

None. This is the first task.

---

## Acceptance Criteria

- [ ] GitHub organization `fox-in-the-box-ai` exists and is accessible
- [ ] Repository `fox-in-the-box-ai/fox-in-the-box` exists as a fresh (empty or minimal) repo with `main` as the default branch
- [ ] Repository `fox-in-the-box-ai/hermes-agent` exists as a GitHub fork of `NousResearch/hermes-agent`, default branch `main`, synced with upstream
- [ ] Repository `fox-in-the-box-ai/hermes-webui` exists as a GitHub fork of the upstream hermes-webui repo, default branch `main`, synced with upstream
- [ ] All three repositories are visible under the `fox-in-the-box-ai` org
- [ ] Stan (or designated collaborators) have admin access to all three repositories

---

## Implementation Steps

1. **Create the GitHub organization**
   - Go to [https://github.com/organizations/plan](https://github.com/organizations/plan)
   - Create organization with the name: `fox-in-the-box-ai`
   - Choose the free tier unless a paid plan is required
   - Set Stan's account as the org owner

2. **Create the monorepo**
   - Go to [https://github.com/new](https://github.com/new)
   - Owner: `fox-in-the-box-ai`
   - Repository name: `fox-in-the-box`
   - Visibility: Public (or Private — confirm with team)
   - Initialize with a README (so `main` branch is created)
   - Default branch: `main`
   - Do **not** add .gitignore or license here — that is handled in task 02

3. **Fork hermes-agent**
   - Navigate to `https://github.com/NousResearch/hermes-agent`
   - Click **Fork**
   - Owner: `fox-in-the-box-ai`
   - Repository name: `hermes-agent` (keep default)
   - Ensure **"Copy the `main` branch only"** is checked (or fork all branches — confirm with team; `main` is sufficient for now)
   - Click **Create fork**

4. **Fork hermes-webui**
   - **⚠️ BLOCKED — Stan will set up fork repos manually. Skip this step.**
     The upstream hermes-webui URL will be confirmed by Stan before work begins.
     When available it will appear at `https://github.com/fox-in-the-box-ai/hermes-webui`.
     Do not proceed with this step until the fork URL is provided.
   - *(For reference when unblocked:)* Click **Fork** on the upstream repo, set
     Owner: `fox-in-the-box-ai`, Repository name: `hermes-webui`, default branch `main`

5. **Verify org membership and access**
   - Confirm all three repos appear at `https://github.com/fox-in-the-box-ai`
   - Invite any additional collaborators via **Org Settings → Members** if needed

---

## AI Agent Verification Steps

After Stan confirms this task is complete, an AI agent will verify the following:

```bash
# 1. Clone all three repos and confirm they exist
git clone https://github.com/fox-in-the-box-ai/fox-in-the-box.git
git clone https://github.com/fox-in-the-box-ai/hermes-agent.git
git clone https://github.com/fox-in-the-box-ai/hermes-webui.git

# 2. Confirm default branch is main on each
git -C fox-in-the-box branch -r
git -C hermes-agent branch -r
git -C hermes-webui branch -r

# 3. Confirm fork remotes point to correct upstreams
git -C hermes-agent remote -v
# Expected: origin -> fox-in-the-box-ai/hermes-agent
# (upstream can be added in task 02)

git -C hermes-webui remote -v
# Expected: origin -> fox-in-the-box-ai/hermes-webui
```

The agent will report pass/fail for each check and flag any missing repos or misconfigured branches before tasks 02–05 begin.

---

## Notes

- **This task blocks tasks 02–05.** No monorepo scaffold, submodule wiring, or branch strategy work can begin until all three repos exist.
- **Tasks 02–05 can run in parallel** once this task is marked complete.
- Forks are plain GitHub forks at this stage — submodule configuration is handled in **task 02**.
- Do **not** create any feature branches here — branch strategy is defined in **task 02**.
- Do **not** add GitHub Actions workflows here — CI/CD is a later task.
- The `fox-in-the-box` monorepo is a **fresh repo**, not a fork of anything.
- If the upstream hermes-webui URL is not yet confirmed, **skip step 4**. Stan will set up the fork manually and update this doc when ready. The task can be marked complete without the hermes-webui fork — Task 02 will reference it via submodule once available.
