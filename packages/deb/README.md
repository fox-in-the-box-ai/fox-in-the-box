# Fox in the Box — Deb Packages

`.deb` packages for Ubuntu 22.04/24.04 and Zorin OS 16/17.

## User install

### Via the apt repo — not yet reachable

Packages have published to the repo bucket since v0.7.59. The domain is
`foxinthebox.io` (registered, on Cloudflare); the `apt.` subdomain just
needs the R2 custom-domain attach — **use the direct .deb download below
until `apt.foxinthebox.io` resolves.** Once live (verify the key
fingerprint against the one published in this repo before trusting it):

```bash
# Add the signing key + repo once
curl -fsSL https://apt.foxinthebox.io/gpg | sudo gpg --dearmor -o /usr/share/keyrings/foxinthebox.gpg
echo "deb [signed-by=/usr/share/keyrings/foxinthebox.gpg] https://apt.foxinthebox.io stable main" | sudo tee /etc/apt/sources.list.d/foxinthebox.list

sudo apt update && sudo apt install foxinthebox
```

Releases publish to the repo automatically via `release.yml`'s `publish-apt` job (reprepro → Cloudflare R2).

### Direct .deb download (alternative)

Download the `.deb` for your architecture from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest):

```bash
sudo apt install ./foxinthebox_<version>_<arch>.deb
```

### From a local .deb file

Always use `apt install` (not `dpkg -i`) to ensure dependencies are resolved:

```bash
sudo apt install ./foxinthebox_<version>_<arch>.deb
```

## Infrastructure setup

The one-time GPG keygen, R2 bucket bootstrap, and GitHub-secrets inventory
live in [`docs/ops/apt-repo-setup.md`](../../docs/ops/apt-repo-setup.md) —
that ops doc is the maintained copy; this README intentionally doesn't
duplicate it.

## Building locally

```bash
# Requires dpkg-dev: sudo apt install dpkg-dev
bash packages/deb/build.sh amd64
# Output: dist/foxinthebox_<version>_amd64.deb
```

## Publishing manually

```bash
export GPG_PRIVATE_KEY="$(cat my-private-key.asc)"
export GPG_KEY_ID="ABCD1234..."
export R2_ACCOUNT_ID="..."
export R2_ACCESS_KEY="..."
export R2_SECRET_KEY="..."
bash packages/deb/publish-apt.sh

# Dry run (no changes):
DRY_RUN=1 bash packages/deb/publish-apt.sh
```
