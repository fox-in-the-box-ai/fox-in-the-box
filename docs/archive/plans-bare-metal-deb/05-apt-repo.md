# 05 — Apt Repository Hosting

## Stack: reprepro + Cloudflare R2

| Choice | Rationale |
|--------|-----------|
| **reprepro** | Mature, simple, generates valid apt repo structure + Release files |
| **Cloudflare R2** | Free egress, S3-compatible, CDN-backed, works with `rclone` |
| **GPG signing** | Standard apt requirement — CI signs with a dedicated key |

Alternative considered: **aptly** — more powerful but overkill for one package. reprepro is simpler to operate.

## Directory structure on R2

```
r2://foxinthebox-apt/
├── conf/
│   └── distributions       ← reprepro config (not served publicly)
├── dists/
│   └── stable/
│       ├── Release          ← signed, lists all components
│       ├── Release.gpg      ← detached signature
│       ├── InRelease        ← clearsigned (modern apt prefers this)
│       └── main/
│           ├── binary-amd64/
│           │   └── Packages.gz
│           └── binary-arm64/
│               └── Packages.gz
└── pool/
    └── main/f/foxinthebox/
        ├── foxinthebox_0.8.0_amd64.deb
        └── foxinthebox_0.8.0_arm64.deb
```

## reprepro distributions config

```
Origin: Fox in the Box
Label: Fox in the Box
Codename: stable
Architectures: amd64 arm64
Components: main
Description: Fox in the Box apt repository
SignWith: FOXINTHEBOX_GPG_KEY_ID
```

## User setup (one-time)

```bash
# 1. Add GPG key
curl -fsSL https://apt.foxinthebox.ai/gpg.asc \
  | sudo gpg --dearmor -o /usr/share/keyrings/foxinthebox.gpg

# 2. Add source
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/foxinthebox.gpg] \
  https://apt.foxinthebox.ai stable main" \
  | sudo tee /etc/apt/sources.list.d/foxinthebox.list

# 3. Install
sudo apt update && sudo apt install foxinthebox
```

This can be wrapped in a one-liner: `curl -fsSL https://foxinthebox.ai/install-deb.sh | bash`
That script does the 3 steps above. The Docker install path stays at `install.sh`.

## CI workflow: publish to R2

```yaml
# .github/workflows/release.yml  (new step, after building .deb)
- name: Publish .deb to apt repo
  env:
    GPG_PRIVATE_KEY: ${{ secrets.APT_GPG_PRIVATE_KEY }}
    GPG_KEY_ID:      ${{ secrets.APT_GPG_KEY_ID }}
    R2_ACCOUNT_ID:   ${{ secrets.R2_ACCOUNT_ID }}
    R2_ACCESS_KEY:   ${{ secrets.R2_ACCESS_KEY }}
    R2_SECRET_KEY:   ${{ secrets.R2_SECRET_KEY }}
    R2_BUCKET:       foxinthebox-apt
  run: |
    # Install tools
    sudo apt-get install -y reprepro gpg rclone

    # Import GPG key
    echo "$GPG_PRIVATE_KEY" | gpg --batch --import

    # Pull current repo state from R2
    rclone sync r2:$R2_BUCKET ./apt-repo \
      --s3-provider=Cloudflare \
      --s3-access-key-id=$R2_ACCESS_KEY \
      --s3-secret-access-key=$R2_SECRET_KEY \
      --s3-endpoint=https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com

    # Add new .deb to reprepro
    reprepro -b ./apt-repo includedeb stable dist/foxinthebox_*_amd64.deb
    reprepro -b ./apt-repo includedeb stable dist/foxinthebox_*_arm64.deb

    # Push updated repo back to R2
    rclone sync ./apt-repo r2:$R2_BUCKET \
      --s3-provider=Cloudflare \
      --s3-access-key-id=$R2_ACCESS_KEY \
      --s3-secret-access-key=$R2_SECRET_KEY \
      --s3-endpoint=https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com
```

## GPG key management

- Generate a dedicated signing key (not a personal key): `gpg --batch --gen-key`
- Store private key in GitHub secret `APT_GPG_PRIVATE_KEY` (armored export)
- Store key ID in `APT_GPG_KEY_ID`
- Export public key to repo at `https://apt.foxinthebox.ai/gpg.asc` (static file in R2)

## Cloudflare R2 + custom domain setup

1. Create R2 bucket `foxinthebox-apt`
2. Enable public access on bucket
3. Add CNAME `apt.foxinthebox.ai` → R2 bucket's public URL
4. Done — R2 serves static files directly, no origin server needed

Cost: R2 free tier covers 10GB storage + 10M requests/month. More than enough for one package with ~1K installs/month.

## Retention policy

Keep last 5 versions per architecture in the pool. Old `.deb` files are removed by reprepro automatically when `includedeb` is called with `reprepro --delete` for versions older than N. Set in CI as a post-publish cleanup step.
