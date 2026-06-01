# apt.foxinthebox.ai — Setup Instructions

Instructions for configuring the GitHub CI pipeline and Cloudflare R2 bucket
to publish `.deb` packages to `apt.foxinthebox.ai`.

---

## 1. Cloudflare R2 Bucket

### Create the bucket

1. Log in to Cloudflare Dashboard → R2 Object Storage
2. Create bucket: `foxinthebox-apt`
3. Region: auto (or closest to users)

### Create R2 API token

1. R2 → Manage R2 API Tokens → Create API Token
2. Permissions: Object Read & Write
3. Specify bucket: `foxinthebox-apt`
4. Note the **Access Key ID** and **Secret Access Key**

### Configure custom domain

1. R2 bucket settings → Custom Domains → Add
2. Enter: `apt.foxinthebox.ai`
3. Cloudflare will auto-provision DNS + TLS
4. Cache settings: cache everything, default TTL (R2 handles invalidation)

---

## 2. GPG Signing Key

The apt repo needs a GPG key to sign package metadata. Users verify
packages against this key.

```bash
# Generate a dedicated key (no passphrase — CI needs non-interactive signing)
gpg --batch --gen-key <<EOF
Key-Type: RSA
Key-Length: 4096
Name-Real: Fox in the Box
Name-Email: security@foxinthebox.ai
Expire-Date: 0
%no-protection
EOF

# Export the private key (armored) for GitHub Secrets
gpg --armor --export-secret-keys security@foxinthebox.ai > apt-signing-key.asc

# Get the key ID
gpg --list-keys --keyid-format long security@foxinthebox.ai
# Note the 16-char key ID (e.g., ABCDEF1234567890)

# Export the public key for the apt repo
gpg --armor --export security@foxinthebox.ai > foxinthebox-apt.gpg.asc
```

Host the public key at `https://apt.foxinthebox.ai/gpg` (upload to R2 bucket
root as `gpg`).

---

## 3. GitHub Secrets

Add these secrets to the `fox-in-the-box` repository:

| Secret Name | Value | Where from |
|-------------|-------|-----------|
| `APT_GPG_PRIVATE_KEY` | Contents of `apt-signing-key.asc` | Step 2 |
| `APT_GPG_KEY_ID` | 16-char key ID (e.g., `ABCDEF1234567890`) | Step 2 |
| `R2_ACCOUNT_ID` | Cloudflare account ID (Dashboard → Account Home → right sidebar) | Cloudflare |
| `R2_ACCESS_KEY` | R2 API token Access Key ID | Step 1 |
| `R2_SECRET_KEY` | R2 API token Secret Access Key | Step 1 |

Path: Repository → Settings → Secrets and variables → Actions → New repository secret

---

## 4. How the Pipeline Works

On tag push (`vX.Y.Z`), `release.yml` runs:

```
build-deb (amd64 + arm64)
    ↓
deb-smoke-test (dpkg install verification)
    ↓
publish-apt (reprepro → R2 sync)
    ↓
release (GitHub Release with .deb attached)
```

### publish-apt.sh flow

1. Installs `reprepro`, `gpg`, `rclone` via apt
2. Imports GPG private key from `APT_GPG_PRIVATE_KEY` secret
3. Configures rclone for R2 via environment variables (no credentials on disk)
4. Pulls current repo state from R2 (`rclone sync r2:foxinthebox-apt ./apt-repo`)
5. Bootstraps reprepro config on first run (creates `conf/distributions`)
6. Adds `.deb` files via `reprepro includedeb stable <file>`
7. Pushes updated repo back to R2

### What gets published

```
apt.foxinthebox.ai/
├── dists/
│   └── stable/
│       └── main/
│           ├── binary-amd64/Packages.gz
│           └── binary-arm64/Packages.gz
├── pool/
│   └── main/
│       └── f/foxinthebox/
│           ├── foxinthebox_0.7.44_amd64.deb
│           └── foxinthebox_0.7.44_arm64.deb
├── gpg                              ← public signing key
└── conf/                            ← reprepro metadata (not user-facing)
```

---

## 5. User Install Instructions

After the repo is live, users run:

```bash
# Add the GPG key
curl -fsSL https://apt.foxinthebox.ai/gpg | sudo gpg --dearmor \
    -o /usr/share/keyrings/foxinthebox.gpg

# Add the repository
echo "deb [signed-by=/usr/share/keyrings/foxinthebox.gpg] https://apt.foxinthebox.ai stable main" \
    | sudo tee /etc/apt/sources.list.d/foxinthebox.list

# Install
sudo apt update && sudo apt install foxinthebox

# Fox is now running at http://localhost:8787
```

Upgrade: `sudo apt update && sudo apt upgrade foxinthebox`

---

## 6. Verification Checklist

After first setup, verify:

- [ ] `curl -sf https://apt.foxinthebox.ai/gpg | head -1` returns `-----BEGIN PGP PUBLIC KEY BLOCK-----`
- [ ] `curl -sf https://apt.foxinthebox.ai/dists/stable/main/binary-amd64/Packages.gz | gunzip | head` shows package metadata
- [ ] On a clean Ubuntu 22.04 VM: install instructions above succeed
- [ ] `dpkg -l foxinthebox` shows installed version
- [ ] `systemctl status foxinthebox` shows active/running
- [ ] `curl -sf http://localhost:8787/health` returns `{"status":"ok"}`
- [ ] GitHub Release page shows `.deb` files attached alongside `.exe` and `.dmg`

---

## 7. Troubleshooting

**`publish-apt` job fails with "GPG_PRIVATE_KEY not set":**
The secret is not configured in the repository. See Step 3.

**`reprepro: already in pool` error:**
The same version `.deb` was already published. Bump VERSION before re-tagging.

**Users get "NO_PUBKEY" on apt update:**
The public GPG key at `apt.foxinthebox.ai/gpg` is missing or the R2 custom
domain isn't configured. Check Step 1.

**rclone sync hangs or 403:**
R2 API token lacks write permission on the `foxinthebox-apt` bucket. Recreate
the token with Object Read & Write on that specific bucket.
