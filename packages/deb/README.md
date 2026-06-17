# Fox in the Box — Deb Packages

`.deb` packages for Ubuntu 22.04/24.04 and Zorin OS 16/17.

## User install

Download the `.deb` for your architecture from the [latest release](https://github.com/fox-in-the-box-ai/fox-in-the-box/releases/latest):

```bash
sudo apt install ./foxinthebox_<version>_<arch>.deb
```

> **apt repo (coming in v0.7.49).** `apt.foxinthebox.ai` will provide `apt install foxinthebox` once GPG signing and R2 hosting are configured. Tracked in #539. Until then, download the `.deb` from GitHub Releases.

### From a local .deb file

Always use `apt install` (not `dpkg -i`) to ensure dependencies are resolved:

```bash
sudo apt install ./foxinthebox_<version>_<arch>.deb
```

## One-time infrastructure setup

### Generate GPG signing key pair

```bash
# Generate (no passphrase — for CI use)
gpg --batch --full-gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Subkey-Type: RSA
Subkey-Length: 4096
Name-Real: Fox in the Box
Name-Email: apt@foxinthebox.ai
Expire-Date: 0
%no-protection
%commit
EOF

# Get key ID
gpg --list-secret-keys apt@foxinthebox.ai

# Export private key (store as GitHub secret APT_GPG_PRIVATE_KEY)
gpg --armor --export-secret-keys <KEY_ID>

# Export public key (upload to R2 as gpg.asc)
gpg --armor --export <KEY_ID> > gpg.asc
# rclone copyto gpg.asc r2:foxinthebox-apt/gpg.asc
```

### Bootstrap Cloudflare R2 bucket

1. Create bucket `foxinthebox-apt` in Cloudflare R2
2. Enable public access on the bucket
3. Add CNAME: `apt.foxinthebox.ai` → R2 bucket public URL
4. Create R2 API token with Read+Write access to `foxinthebox-apt`
5. Upload `gpg.asc` to bucket root

### GitHub secrets required

| Secret | Value |
|--------|-------|
| `APT_GPG_PRIVATE_KEY` | `gpg --armor --export-secret-keys <KEY_ID>` |
| `APT_GPG_KEY_ID` | GPG key fingerprint |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY` | R2 API token access key |
| `R2_SECRET_KEY` | R2 API token secret key |

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
