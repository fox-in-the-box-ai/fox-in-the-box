# Bare-Metal Install + .deb Package Plan

**Goal:** Run Fox in the Box on Ubuntu / Zorin OS without Docker — delivered as an `apt`-installable `.deb` with a hosted apt repository, sharing all install logic with the existing Docker path.

**Why this approach:** Zorin IS Ubuntu under the hood (22.04 / 24.04 LTS base). One `.deb` covers both. The `apt install / upgrade / remove` lifecycle gives users the update story they already know, and gives us the update story we need without a custom updater daemon.

## Doc index

| Doc | Contents |
|-----|----------|
| [01-current-state.md](01-current-state.md) | Source audit — what the container does today, line by line |
| [02-target.md](02-target.md) | Target architecture: install-core, .deb, apt repo |
| [03-install-core.md](03-install-core.md) | install-core.sh design: shared logic, path parameterization |
| [04-deb-package.md](04-deb-package.md) | .deb structure, postinst/postrm, control file |
| [05-apt-repo.md](05-apt-repo.md) | Apt repo hosting: reprepro + Cloudflare R2 |
| [06-ci.md](06-ci.md) | CI: build .deb on release, sign, push to repo |
| [07-phase-plan.md](07-phase-plan.md) | Phased implementation — milestones and exit criteria |

## TL;DR per phase

| Phase | Deliverable | Effort |
|-------|-------------|--------|
| 1 | `install-core.sh` — extracted, tested, path-parameterized | ~3h agent |
| 2 | `.deb` package wrapping install-core + systemd units | ~2h agent |
| 3 | Apt repo on R2, `apt.foxinthebox.ai` | ~2h agent |
| 4 | CI: build + sign + publish `.deb` on every release | ~1h agent |
| **Total** | | **~8h agent** |

## Key decisions

- **Ubuntu 22.04 + 24.04** as targets (covers Zorin 16/17 respectively — Zorin is a reskin)
- **No Snap, no AppImage** — apt is what VPS users and Zorin users already have
- **Dockerfile stays as-is** — it becomes a consumer of install-core.sh, not replaced
- **Tailscale stays** — `tailscale` package installed as a system dep, same as now
- **`/opt/foxinthebox/`** as the app root (replaces `/app/` in the container)
- **`~/.foxinthebox/`** as user data dir (matches existing Docker default, no migration needed)
- **systemd units** already exist in `packages/scripts/` — needs path substitution only
