     1|# Task 07: Install Scripts
     2|
     3|| Field          | Value                                                                      |
     4||----------------|----------------------------------------------------------------------------|
     5|| **Status**     | Ready                                                                      |
     6|| **Executor**   | AI agent                                                                   |
     7|| **Depends on** | Task 02 (monorepo scaffold), Task 03 (image published to GHCR)             |
     8|| **Parallel**   | Task 06 (Electron wrapper) — can run concurrently                          |
     9|| **Blocks**     | —                                                                          |
    10|| **Path**       | `packages/scripts/`                                                        |
    11|
    12|---
    13|
    14|## Summary
    15|
    16|Write `packages/scripts/install.sh` — a single Bash script that detects whether it is
    17|running on Linux or macOS, installs Docker if absent, pulls the published container
    18|image, prompts the user to choose a network-access mode (port-only, Tailscale, or
    19|both), starts the container, and then installs the appropriate service manager
    20|integration (systemd on Linux, launchd on macOS) so that the container starts
    21|automatically on boot and can be updated via a sentinel-file trigger.
    22|
    23|No Electron, no GUI installer. The entire install surface is a single shell script
    24|plus static service-unit files committed alongside it.
    25|
    26|---
    27|
    28|## Prerequisites
    29|
    30|1. **Task 02 complete** — `packages/scripts/` directory exists in the monorepo.
    31|2. **Task 03 complete** — `ghcr.io/fox-in-the-box-ai/cloud:stable` has been pushed to
    32|   GHCR and is publicly pullable (or the token is in `~/.docker/config.json`).
    33|
    34|---
    35|
    36|## File Inventory
    37|
    38|| File (relative to repo root)                              | Description                          |
    39||-----------------------------------------------------------|--------------------------------------|
    40|| `packages/scripts/install.sh`                             | Main install script                  |
    41|| `packages/scripts/foxinthebox.service`                    | systemd container-run unit           |
    42|| `packages/scripts/foxinthebox-updater.service`            | systemd one-shot update unit         |
    43|| `packages/scripts/foxinthebox-updater.path`               | systemd path-watch unit              |
    44|| `packages/scripts/io.foxinthebox.plist`                   | launchd agent plist (macOS)          |
    45|| `tests/container/test_install.bats`                       | Bats test suite (6 test cases)       |
    46|
    47|---
    48|
    49|## Implementation
    50|
    51|### `packages/scripts/install.sh`
    52|
    53|```bash
    54|#!/usr/bin/env bash
    55|# install.sh — Fox in the Box installer (Linux & macOS)
    56|# Usage: curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
    57|#   or:  bash install.sh
    58|set -euo pipefail
    59|
    60|##############################################################################
    61|# Helpers
    62|##############################################################################
    63|BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    64|RED='\033[0;31m'; NC='\033[0m'
    65|
    66|info()    { echo -e "${BLUE}[fox]${NC} $*"; }
    67|success() { echo -e "${GREEN}[fox]${NC} $*"; }
    68|warn()    { echo -e "${YELLOW}[fox]${NC} $*"; }
    69|die()     { echo -e "${RED}[fox] ERROR:${NC} $*" >&2; exit 1; }
    70|
    71|IMAGE="ghcr.io/fox-in-the-box-ai/cloud:stable"
    72|CONTAINER="fox-in-the-box"
    73|
    74|##############################################################################
    75|# 1. Detect OS
    76|##############################################################################
    77|OS="$(uname -s)"
    78|case "$OS" in
    79|  Linux)  PLATFORM="linux"  ;;
    80|  Darwin) PLATFORM="macos"  ;;
    81|  *)      die "Unsupported operating system: $OS" ;;
    82|esac
    83|info "Detected platform: $PLATFORM"
    84|
    85|# ── Platform-specific default paths ──────────────────────────────────────────
    86|# APP_DATA_DIR  : bind-mounted as /data inside the container.
    87|#                 Holds repos, config, runtime data, cache.
    88|# WORKSPACE_DIR : lives on the host only — NEVER mounted into the container.
    89|#                 The user's own documents and project files.
    90|#
    91|# These two directories must NEVER be the same path or nested inside each other.
    92|
    93|if [[ "$PLATFORM" == "linux" ]]; then
    94|  DEFAULT_DATA_DIR="$HOME/.foxinthebox"
    95|  DEFAULT_WORKSPACE_DIR="$HOME/Fox in the Box"
    96|elif [[ "$PLATFORM" == "macos" ]]; then
    97|  DEFAULT_DATA_DIR="$HOME/Library/Application Support/Fox in the Box"
    98|  DEFAULT_WORKSPACE_DIR="$HOME/Documents/Fox in the Box"
    99|fi
   100|
   101|DATA_DIR="${FOX_DATA_DIR:-$DEFAULT_DATA_DIR}"
   102|WORKSPACE_DIR="${FOX_WORKSPACE_DIR:-$DEFAULT_WORKSPACE_DIR}"
   103|
   104|##############################################################################
   105|# 2. Check / install Docker
   106|##############################################################################
   107|_docker_running() {
   108|  docker info >/dev/null 2>&1
   109|}
   110|
   111|if ! command -v docker &>/dev/null || ! _docker_running; then
   112|  warn "Docker not found or not running — installing…"
   113|
   114|  if [[ "$PLATFORM" == "linux" ]]; then
   115|    curl -fsSL https://get.docker.com | sh \
   116|      || die "Docker install script failed. Fix the error above and re-run."
   117|    sudo systemctl start docker \
   118|      || die "Failed to start Docker daemon."
   119|    # Allow current user to use Docker without sudo (takes effect next login)
   120|    if ! groups "$USER" | grep -q docker; then
   121|      sudo usermod -aG docker "$USER"
   122|      warn "Added $USER to the 'docker' group. You may need to log out and back in."
   123|      warn "Re-running this installer under 'sudo' for now…"
   124|      DOCKER_CMD="sudo docker"
   125|    fi
   126|  elif [[ "$PLATFORM" == "macos" ]]; then
   127|    if command -v brew &>/dev/null; then
   128|      brew install --cask docker \
   129|        || die "Homebrew failed to install Docker Desktop."
   130|      info "Docker Desktop installed. Please launch it from /Applications, then re-run this installer."
   131|      exit 1
   132|    else
   133|      die "Docker is not installed and Homebrew is not available.\n\
   134|Please install Docker Desktop manually from https://docs.docker.com/desktop/mac/install/\n\
   135|then re-run this installer."
   136|    fi
   137|  fi
   138|
   139|  # Final check
   140|  _docker_running || die "Docker installed but daemon is still not responding. Start Docker and re-run."
   141|fi
   142|
   143|DOCKER_CMD="${DOCKER_CMD:-docker}"
   144|success "Docker is ready."
   145|
   146|##############################################################################
   147|# 3. Pull image
   148|##############################################################################
   149|info "Pulling image: $IMAGE"
   150|$DOCKER_CMD pull "$IMAGE" \
   151|  || die "Failed to pull $IMAGE. Check your network connection or GHCR credentials."
   152|success "Image pulled."
   153|
   154|##############################################################################
   155|# 4. Prompt: network access mode
   156|##############################################################################
   157|_explain_tailscale() {
   158|  echo
   159|  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
   160|  echo "  What is Tailscale?"
   161|  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
   162|  echo
   163|  echo "  Tailscale is a free VPN tool that lets you securely"
   164|  echo "  access Fox in the Box from anywhere — your phone,"
   165|  echo "  laptop, or any other device — without opening ports"
   166|  echo "  in your firewall or dealing with IP addresses."
   167|  echo
   168|  echo "  With Tailscale:"
   169|  echo "    • You get a stable private URL like https://fox.your-name.ts.net"
   170|  echo "    • HTTPS is set up automatically (no certificates to manage)"
   171|  echo "    • Only your approved devices can connect — nothing is public"
   172|  echo "    • Free for personal use (up to 100 devices)"
   173|  echo
   174|  echo "  Without Tailscale (port only):"
   175|  echo "    • Fox in the Box is available at http://localhost:8787"
   176|  echo "    • Accessible on your local network if your firewall allows it"
   177|  echo "    • No remote access unless you set up your own reverse proxy"
   178|  echo
   179|  echo "  Not sure? Choose [1] Port only for now — you can add"
   180|  echo "  Tailscale later by re-running this script."
   181|  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
   182|  echo
   183|}
   184|
   185|_prompt_access_mode() {
   186|  while true; do
   187|    echo
   188|    echo "How do you want to access Fox in the Box?"
   189|    echo "  [1] Port only (http://localhost:8787 + LAN if firewall permits)"
   190|    echo "  [2] Tailscale only (private HTTPS from anywhere, free)"
   191|    echo "  [3] Both (port binding + Tailscale)"
   192|    echo "  [?] What is Tailscale? Explain more"
   193|    echo
   194|    read -rp "Enter 1, 2, 3 or ? [default: 1]: " ACCESS_MODE
   195|    ACCESS_MODE="${ACCESS_MODE:-1}"
   196|
   197|    case "$ACCESS_MODE" in
   198|      1) PORT_BIND="-p 0.0.0.0:8787:8787"; USE_TAILSCALE=false; break ;;
   199|      2) PORT_BIND="-p 127.0.0.1:8787:8787"; USE_TAILSCALE=true;  break ;;
   200|      3) PORT_BIND="-p 0.0.0.0:8787:8787";  USE_TAILSCALE=true;  break ;;
   201|      "?"|"help"|"explain"|"more"|"what") _explain_tailscale ;;
   202|      *) warn "Invalid selection: '$ACCESS_MODE'. Please enter 1, 2, 3 or ?." ;;
   203|    esac
   204|  done
   205|}
   206|
   207|_prompt_access_mode
   208|
   209|##############################################################################
   210|# 5. Create host directories
   211|##############################################################################
   212|# App data dir — bind-mounted as /data inside the container
   213|mkdir -p "$DATA_DIR"
   214|
   215|# Workspace dir — host only, NEVER mounted into container
   216|# This is where the user's own project files and exports live
   217|mkdir -p "$WORKSPACE_DIR"
   218|
   219|if $DOCKER_CMD ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
   220|  warn "Container '$CONTAINER' already exists — stopping and removing it for a clean install."
   221|  $DOCKER_CMD stop "$CONTAINER" >/dev/null 2>&1 || true
   222|  $DOCKER_CMD rm   "$CONTAINER" >/dev/null 2>&1 || true
   223|fi
   224|
   225|info "Starting container…"
   226|# shellcheck disable=SC2086
   227|$DOCKER_CMD run -d \
   228|  --name "$CONTAINER" \
   229|  --restart unless-stopped \
   230|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   231|  --sysctl net.ipv4.ip_forward=1 \
   232|  -v "$DATA_DIR":/data \
   233|  $PORT_BIND \
   234|  "$IMAGE" \
   235|  || die "Failed to start container."
   236|
   237|success "Container '$CONTAINER' is running."
   238|
   239|##############################################################################
   240|# 7. Tailscale authentication
   241|##############################################################################
   242|if [[ "$USE_TAILSCALE" == "true" ]]; then
   243|  info "Waiting for Tailscale login URL (up to 60 s)…"
   244|  LOGIN_URL=""
   245|  DEADLINE=$(( $(date +%s) + 60 ))
   246|  while [[ $(date +%s) -lt $DEADLINE ]]; do
   247|    LOG_LINE="$($DOCKER_CMD logs --tail 50 "$CONTAINER" 2>&1 || true)"
   248|    LOGIN_URL="$(echo "$LOG_LINE" | grep -oE 'https://login\.tailscale\.com/a/[A-Za-z0-9]+' | head -1 || true)"
   249|    [[ -n "$LOGIN_URL" ]] && break
   250|    sleep 2
   251|  done
   252|
   253|  if [[ -z "$LOGIN_URL" ]]; then
   254|    warn "Tailscale login URL not seen in logs within 60 s."
   255|    warn "Run:  docker logs $CONTAINER | grep tailscale"
   256|  else
   257|    echo
   258|    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
   259|    echo "  Tailscale login URL:"
   260|    echo "  $LOGIN_URL"
   261|    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
   262|    if command -v qrencode &>/dev/null; then
   263|      info "QR code (scan with Tailscale mobile app):"
   264|      qrencode -t ANSIUTF8 "$LOGIN_URL"
   265|    else
   266|      info "(Install 'qrencode' to display a QR code here.)"
   267|    fi
   268|
   269|    # Poll until authenticated
   270|    info "Waiting for Tailscale to connect…"
   271|    CONNECTED=false
   272|    DEADLINE=$(( $(date +%s) + 180 ))
   273|    while [[ $(date +%s) -lt $DEADLINE ]]; do
   274|      BACKEND_STATE="$($DOCKER_CMD exec "$CONTAINER" tailscale status --json 2>/dev/null \
   275|                       | grep -oE '"BackendState":"[^"]+"' \
   276|                       | grep -oE '[^"]+$' || true)"
   277|      if [[ "$BACKEND_STATE" == "Running" ]]; then
   278|        CONNECTED=true
   279|        break
   280|      fi
   281|      sleep 3
   282|    done
   283|
   284|    if [[ "$CONNECTED" == "true" ]]; then
   285|      TAILNET_URL="$($DOCKER_CMD exec "$CONTAINER" tailscale status --json 2>/dev/null \
   286|                     | grep -oE '"DNSName":"[^"]+"' | head -1 \
   287|                     | grep -oE '"[^"]+$' | tr -d '"' || true)"
   288|      if [[ -n "$TAILNET_URL" ]]; then
   289|        success "Tailscale connected! Access Fox at:  https://${TAILNET_URL%\.}"
   290|      else
   291|        success "Tailscale connected!"
   292|      fi
   293|    else
   294|      warn "Tailscale not yet confirmed running. Check with: docker exec $CONTAINER tailscale status"
   295|    fi
   296|  fi
   297|fi
   298|
   299|##############################################################################
   300|# 8 / 9. Install service manager integration
   301|##############################################################################
   302|SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   303|
   304|if [[ "$PLATFORM" == "linux" ]]; then
   305|  info "Installing systemd units…"
   306|  SYSTEMD_DIR="/etc/systemd/system"
   307|
   308|  sudo cp "$SCRIPT_DIR/foxinthebox.service"           "$SYSTEMD_DIR/"
   309|  sudo cp "$SCRIPT_DIR/foxinthebox-updater.service"   "$SYSTEMD_DIR/"
   310|  sudo cp "$SCRIPT_DIR/foxinthebox-updater.path"      "$SYSTEMD_DIR/"
   311|
   312|  # Substitute __DATA_DIR__ placeholder with the actual data directory
   313|  sudo sed -i "s|__DATA_DIR__|${DATA_DIR}|g" "$SYSTEMD_DIR/foxinthebox.service"
   314|  sudo sed -i "s|__DATA_DIR__|${DATA_DIR}|g" "$SYSTEMD_DIR/foxinthebox-updater.path"
   315|
   316|  sudo systemctl daemon-reload
   317|  sudo systemctl enable foxinthebox
   318|  sudo systemctl enable foxinthebox-updater.path
   319|  success "systemd units installed and enabled."
   320|
   321|elif [[ "$PLATFORM" == "macos" ]]; then
   322|  info "Installing launchd agent…"
   323|  LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
   324|  mkdir -p "$LAUNCH_AGENTS"
   325|  PLIST="$LAUNCH_AGENTS/io.foxinthebox.plist"
   326|
   327|  cp "$SCRIPT_DIR/io.foxinthebox.plist" "$PLIST"
   328|
   329|  # Patch data dir into plist
   330|  sed -i '' "s|__DATA_DIR__|$DATA_DIR|g" "$PLIST"
   331|
   332|  # Unload first (idempotent)
   333|  launchctl unload "$PLIST" 2>/dev/null || true
   334|  launchctl load -w "$PLIST" \
   335|    || die "launchctl failed to load $PLIST"
   336|  success "launchd agent installed and loaded."
   337|fi
   338|
   339|##############################################################################
   340|# 10. Success summary
   341|##############################################################################
   342|echo
   343|echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
   344|success "Fox in the Box is installed!"
   345|echo
   346|echo "  Container  : $CONTAINER"
   347|echo
   348|echo "  App data   : $DATA_DIR"
   349|echo "               (config, repos, runtime data — bind-mounted into container)"
   350|echo
   351|echo "  Workspace  : $WORKSPACE_DIR"
   352|echo "               (your files and projects — NOT inside the container)"
   353|echo
   354|if [[ "$ACCESS_MODE" == "1" || "$ACCESS_MODE" == "3" ]]; then
   355|  echo "  Web UI     : http://localhost:8787"
   356|fi
   357|if [[ "$USE_TAILSCALE" == "true" ]]; then
   358|  echo "  Tailscale  : see Tailscale admin console for HTTPS URL"
   359|fi
   360|echo
   361|echo "  Logs       : docker logs -f $CONTAINER"
   362|echo "  Stop       : docker stop $CONTAINER"
   363|if [[ "$PLATFORM" == "linux" ]]; then
   364|  echo "  Service   : systemctl status foxinthebox"
   365|else
   366|  echo "  Service   : launchctl list io.foxinthebox"
   367|fi
   368|echo
   369|if [[ "$ACCESS_MODE" == "1" || "$ACCESS_MODE" == "3" ]]; then
   370|  warn "FIREWALL NOTE: Port 8787 is bound to 0.0.0.0. Ensure your firewall"
   371|  warn "rules only allow trusted hosts (e.g., 'ufw allow from 192.168.0.0/16 to any port 8787')."
   372|fi
   373|echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
   374|```
   375|
   376|---
   377|
   378|### `packages/scripts/foxinthebox.service`
   379|
   380|```ini
   381|[Unit]
   382|Description=Fox in the Box container
   383|Documentation=https://github.com/fox-in-the-box-ai/fox-in-the-box
   384|After=docker.service network-online.target
   385|Requires=docker.service
   386|
   387|[Service]
   388|Type=simple
   389|Restart=on-failure
   390|RestartSec=10s
   391|
   392|ExecStartPre=-/usr/bin/docker stop fox-in-the-box
   393|ExecStartPre=-/usr/bin/docker rm   fox-in-the-box
   394|ExecStart=/usr/bin/docker run \
   395|  --rm \
   396|  --name fox-in-the-box \
   397|  --cap-add=NET_ADMIN \
     --device /dev/net/tun \
   398|  --sysctl net.ipv4.ip_forward=1 \
   399|  -v __DATA_DIR__:/data \
   400|  -p 0.0.0.0:8787:8787 \
   401|  ghcr.io/fox-in-the-box-ai/cloud:stable
   402|
   403|ExecStop=/usr/bin/docker stop fox-in-the-box
   404|
   405|[Install]
   406|WantedBy=multi-user.target
   407|```
   408|
   409|> **Note:** The `install.sh` script substitutes the `__DATA_DIR__` placeholder
   410|> and patches the `-p` flag at install time if the user chose Tailscale-only or a custom data dir.
   411|
   412|---
   413|
   414|### `packages/scripts/foxinthebox-updater.service`
   415|
   416|```ini
   417|[Unit]
   418|Description=Fox in the Box image updater
   419|After=docker.service network-online.target
   420|Requires=docker.service
   421|
   422|[Service]
   423|Type=oneshot
   424|ExecStart=/bin/bash -c '\
   425|  /usr/bin/docker pull ghcr.io/fox-in-the-box-ai/cloud:stable && \
   426|  /usr/bin/systemctl restart foxinthebox && \
   427|  rm -f /data/update.trigger'
   428|```
   429|
   430|---
   431|
   432|### `packages/scripts/foxinthebox-updater.path`
   433|
   434|```ini
   435|[Unit]
   436|Description=Watch for Fox in the Box update sentinel file
   437|
   438|[Path]
   439|PathExists=__DATA_DIR__/update.trigger
   440|Unit=foxinthebox-updater.service
   441|
   442|[Install]
   443|WantedBy=multi-user.target
   444|```
   445|
   446|---
   447|
   448|### `packages/scripts/io.foxinthebox.plist`
   449|
   450|```xml
   451|<?xml version="1.0" encoding="UTF-8"?>
   452|<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
   453|  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   454|<plist version="1.0">
   455|<dict>
   456|
   457|  <!-- ── Main service ────────────────────────────────────────────────── -->
   458|  <key>Label</key>
   459|  <string>io.foxinthebox</string>
   460|
   461|  <key>ProgramArguments</key>
   462|  <array>
   463|    <string>/usr/local/bin/docker</string>
   464|    <string>run</string>
   465|    <string>--rm</string>
   466|    <string>--name</string>
   467|    <string>fox-in-the-box</string>
   468|    <string>--cap-add=NET_ADMIN</string>
   469|    <string>--sysctl</string>
   470|    <string>net.ipv4.ip_forward=1</string>
   471|    <string>-v</string>
   472|    <string>__DATA_DIR__:/data</string>
   473|    <string>-p</string>
   474|    <string>0.0.0.0:8787:8787</string>
   475|    <string>ghcr.io/fox-in-the-box-ai/cloud:stable</string>
   476|  </array>
   477|
   478|  <key>RunAtLoad</key>
   479|  <true/>
   480|
   481|  <key>KeepAlive</key>
   482|  <true/>
   483|
   484|  <key>StandardOutPath</key>
   485|  <string>__DATA_DIR__/logs/launchd-stdout.log</string>
   486|
   487|  <key>StandardErrorPath</key>
   488|  <string>__DATA_DIR__/logs/launchd-stderr.log</string>
   489|
   490|  <!-- ── Updater (watches sentinel file) ─────────────────────────────── -->
   491|  <key>WatchPaths</key>
   492|  <array>
   493|    <string>__DATA_DIR__/update.trigger</string>
   494|  </array>
   495|
   496|  <!-- When launchd fires on file change it re-runs ProgramArguments.
   497|       The container start will inherently pull latest because
   498|       ExecStartPre pulls the image first via a wrapper script.
   499|       For a cleaner update flow, replace ProgramArguments above with
   500|       a wrapper script that: docker pull → docker stop → docker run.  -->
   501|