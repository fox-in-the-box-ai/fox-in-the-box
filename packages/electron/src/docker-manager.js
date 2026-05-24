'use strict';

const Dockerode = require('dockerode');
const log = require('electron-log');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { exec } = require('child_process');
const { promisify } = require('util');
const execAsync = promisify(exec);

// Rollback escape hatch (v0.7.5): respect FITB_IMAGE if set in the app's
// environment, so users stranded by a bad release can launch with:
//   FITB_IMAGE=ghcr.io/fox-in-the-box-ai/cloud:v0.7.3 /Applications/Fox\ in\ the\ Box.app/...
// on macOS, or set a User env var on Windows, to roll back without waiting
// for a hotfix.
const IMAGE  = process.env.FITB_IMAGE || 'ghcr.io/fox-in-the-box-ai/cloud:stable';
const CNAME  = 'fox-in-the-box';
const PORT   = '8787/tcp';
const ACCESS_MODE_FILE = 'docker-access-mode.json';

let docker = null;
let activeSocket = 'default';
let socketCandidates = [{}];

// Set by isDaemonRunning() when the daemon-not-reachable cause is
// known beyond "no pipe responded." Cleared at the start of each call.
// Callers (startup-orchestrator) check this after a false return to decide
// whether to attempt platform-specific recovery (the existing flow) or
// short-circuit with a user-actionable error (the v0.7.11 #291 path).
let _lastDaemonErrorCode = null;

function dockerError(code, message, cause = null) {
  const err = new Error(message);
  err.code = code;
  if (cause) err.cause = cause;
  return err;
}

function sanitizeLogText(raw) {
  return String(raw || '')
    .replace(/[^\x09\x0A\x0D\x20-\x7E]/g, '')
    .replace(/\r/g, '');
}

function extractSetupStatusFromLogs(logText, context = {}) {
  const lines = sanitizeLogText(logText).split('\n').map((l) => l.trim()).filter(Boolean);
  let currentApp = context.currentApp || null;
  let latestStatus = null;

  for (const line of lines) {
    if (line.includes('[entrypoint] First run detected')) {
      latestStatus = 'Preparing first-run data…';
      continue;
    }
    if (line.includes('[entrypoint] Bootstrap complete')) {
      latestStatus = 'Base setup complete. Preparing Hermes apps…';
      continue;
    }

    if (line.includes('[entrypoint] Hermes apps from container image')) {
      latestStatus = 'Linking Hermes apps from image…';
      continue;
    }

    const cloneMatch = line.match(
      /\[entrypoint\]\s+(?:Cloning|Syncing)\s+(hermes-agent|hermes-webui)/i,
    );
    if (cloneMatch) {
      currentApp = cloneMatch[1];
      latestStatus = `Cloning ${currentApp} repository…`;
      continue;
    }

    if (line.includes('Tag v0.1.0 not found')) {
      latestStatus = `${currentApp || 'Hermes app'} tag not found, using default branch…`;
      continue;
    }

    const updatingMatch = line.match(/Updating files:\s+(\d+)%/i);
    if (updatingMatch && currentApp) {
      latestStatus = `Cloning ${currentApp} repository… ${updatingMatch[1]}%`;
      continue;
    }

    if (line.includes('[entrypoint] Installing Hermes packages from bind mounts')) {
      latestStatus = 'Installing Hermes from dev mounts…';
      continue;
    }

    const installMatch = line.match(/\[entrypoint\]\s+Installing\s+(hermes-agent|hermes-webui)/i);
    if (installMatch) {
      currentApp = installMatch[1];
      latestStatus = `Installing ${currentApp} dependencies…`;
      continue;
    }

    const readyMatch = line.match(/\[entrypoint\]\s+(hermes-agent|hermes-webui)\s+ready\./i);
    if (readyMatch) {
      latestStatus = `${readyMatch[1]} installed. Continuing startup…`;
      continue;
    }
  }

  return { status: latestStatus, currentApp };
}

function getDockerSocketCandidates(platform = process.platform) {
  if (platform === 'win32') {
    return [
      { socketPath: '//./pipe/docker_engine' },
      { socketPath: '//./pipe/dockerDesktopLinuxEngine' },
    ];
  }
  if (platform !== 'darwin') return [{}];
  const homeSocket = path.join(os.homedir(), '.docker', 'run', 'docker.sock');
  const candidates = [];
  if (fs.existsSync('/var/run/docker.sock')) candidates.push({ socketPath: '/var/run/docker.sock' });
  if (fs.existsSync(homeSocket)) candidates.push({ socketPath: homeSocket });
  if (candidates.length === 0) candidates.push({});
  return candidates;
}

/** Initialise the Dockerode client (called once from main.js). */
function init({ platform = process.platform } = {}) {
  socketCandidates = getDockerSocketCandidates(platform);
  const [primary] = socketCandidates;
  docker = new Dockerode(primary);
  activeSocket = primary.socketPath || 'default';
}

/**
 * Returns true if the Docker daemon is reachable.
 * Throws if Dockerode cannot be initialised.
 *
 * On Windows, when both Linux-engine pipes are unreachable, additionally
 * probes `docker info --format '{{.OSType}}'` to detect the case where
 * Docker Desktop is running but in **Windows-containers mode** — Fox needs
 * Linux containers. In that case sets `_lastDaemonErrorCode =
 * 'DOCKER_WINDOWS_CONTAINERS_MODE'` so the orchestrator can short-circuit
 * the recovery flow and surface an actionable error instead of running the
 * unhelpful WSL repair path. See `getLastDaemonErrorCode()` + #291.
 */
async function isDaemonRunning() {
  if (!docker) throw dockerError('DOCKER_NOT_INITIALIZED', 'Docker manager not initialized');
  _lastDaemonErrorCode = null;
  const errors = [];
  for (const candidate of socketCandidates) {
    const socketLabel = candidate.socketPath || 'default';
    if (activeSocket !== socketLabel) {
      docker = new Dockerode(candidate);
      activeSocket = socketLabel;
    }
    try {
      await docker.ping();
      if (errors.length > 0) log.info(`Docker daemon reachable via fallback endpoint ${activeSocket}`);
      return true;
    } catch (err) {
      errors.push(`${socketLabel}: ${err.message}`);
    }
  }
  log.warn('Docker daemon not reachable:', errors.join(' | '), `(socket: ${activeSocket})`);

  // v0.7.11 #291: on Windows, distinguish "Docker not running" from "Docker
  // is running but in Windows-containers mode." The latter needs a totally
  // different recovery (switch mode via tray menu) than the former (start
  // Docker Desktop). bsdigital lost ~30 min in #286 → #288 → #291 because
  // Fox silently took the wrong recovery path.
  if (process.platform === 'win32') {
    try {
      // 3s timeout — `docker info` against a healthy daemon returns in ~50ms;
      // against a degraded daemon it can hang for tens of seconds. Either
      // way, 3s is more than enough for the happy path and bounds the bad path.
      const { stdout } = await execAsync('docker info --format "{{.OSType}}"', {
        timeout: 3000,
        windowsHide: true,
      });
      // Defensive parse: trim + lowercase + endsWith — accounts for stray
      // banner lines some Docker Desktop CLI builds emit before the format
      // output, and for casing variance across 4.x versions.
      const osType = String(stdout).trim().toLowerCase();
      if (osType.endsWith('windows')) {
        _lastDaemonErrorCode = 'DOCKER_WINDOWS_CONTAINERS_MODE';
        log.warn(
          'Docker Desktop is in Windows-containers mode (docker info reports OSType=windows). ' +
          'Fox needs Linux containers — Docker Desktop must be switched to Linux containers ' +
          'mode from its tray menu, then Fox relaunched.',
        );
      }
    } catch (probeErr) {
      // CLI not on PATH (some Docker Desktop installs are GUI-only), daemon
      // hung, exec timeout — any of these mean we can't say the mode is
      // wrong, so fall through to the existing "daemon not running" path
      // and let recovery proceed normally.
      log.debug('Docker mode probe inconclusive:', probeErr.message);
    }
  }

  return false;
}

/** Returns the last error code set by isDaemonRunning(), or null. */
function getLastDaemonErrorCode() {
  return _lastDaemonErrorCode;
}

/**
 * Returns true if the image is already present locally.
 */
async function isImagePresent() {
  const images = await docker.listImages({ filters: { reference: [IMAGE] } });
  return images.length > 0;
}

/**
 * Pull the image with a progress callback.
 * @param {(pct: number) => void} onProgress  0–100
 */
async function pullImage(onProgress) {
  // v0.7.5: removed the pre-pull `docker rmi` step that used to live here.
  // The old "Dockerode.pull() doesn't support --pull=always" rationale was
  // wrong — `docker pull` for a tagged ref already checks the registry
  // manifest and pulls a new digest if :stable has been re-tagged. The rmi
  // step was throwing away the offline fallback for no benefit: every
  // launch became dependent on GHCR uptime, and corporate networks that
  // throttle ghcr.io got a 15-min stall on every restart.
  //
  // If the pull fails now AND no local image exists, the caller (startup
  // orchestrator) surfaces CONTAINER_CREATE_FAILED with a clear hint. If
  // the pull fails BUT a local image exists, the subsequent `docker run`
  // succeeds against the cached image — degraded (no updates this launch)
  // but functional.
  return new Promise((resolve, reject) => {
    docker.pull(IMAGE, (err, stream) => {
      if (err) return reject(err);
      const layers = new Map();
      let lastPct = 0;
      docker.modem.followProgress(stream, onFinish, onEvent);

      function onEvent(evt) {
        if (!evt || !evt.id) return;
        if (evt.progressDetail && evt.progressDetail.total) {
          layers.set(evt.id, {
            current: evt.progressDetail.current || 0,
            total: evt.progressDetail.total || 0,
          });

          let currentSum = 0;
          let totalSum = 0;
          for (const layer of layers.values()) {
            currentSum += layer.current;
            totalSum += layer.total;
          }
          if (totalSum > 0) {
            const rawPct = Math.round((currentSum / totalSum) * 100);
            // Pull events arrive out of order; keep displayed progress monotonic.
            const pct = Math.max(lastPct, Math.min(rawPct, 100));
            lastPct = pct;
            onProgress(pct);
          }
        }
      }
      function onFinish(err2) {
        if (err2) reject(err2);
        else {
          onProgress(100);
          resolve();
        }
      }
    });
  });
}

/**
 * Returns the running container object or null.
 */
async function getRunningContainer() {
  const containers = await docker.listContainers({
    filters: { name: [CNAME] },
  });
  if (containers.length === 0) return null;
  return containers[0];
}

async function getContainerByName({ all = false } = {}) {
  const containers = await docker.listContainers({
    all,
    filters: { name: [CNAME] },
  });
  return containers.length ? containers[0] : null;
}

/**
 * Start the Fox container. Assumes image is already present.
 * Returns the container object.
 */
async function startContainer() {
  const running = await ensureContainerRunning();
  return running.container;
}

function getDataDir() {
  try {
    const { app } = require('electron');
    return process.env.FOX_DATA_DIR || app.getPath('userData');
  } catch (_) {
    return process.env.FOX_DATA_DIR || path.join(os.homedir(), '.foxinthebox');
  }
}

function accessModePrefsPath() {
  return path.join(getDataDir(), ACCESS_MODE_FILE);
}

/**
 * @returns {'1'|'2'|'3'|null}  null = not saved yet (Windows should prompt)
 */
function getSavedAccessMode() {
  try {
    const p = accessModePrefsPath();
    if (!fs.existsSync(p)) return null;
    const raw = JSON.parse(fs.readFileSync(p, 'utf8'));
    const m = String(raw.accessMode || '');
    if (m === '1' || m === '2' || m === '3') return m;
  } catch (_) {
    /* ignore */
  }
  return null;
}

function saveAccessMode(mode) {
  const p = accessModePrefsPath();
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(
    p,
    `${JSON.stringify({ version: 1, accessMode: mode }, null, 0)}\n`,
    'utf8',
  );
}

/**
 * Effective access mode: FOX_ACCESS_MODE env, saved prefs, or default.
 * Mirrors packages/scripts/install.sh (1=port LAN, 2=Tailscale-focused, 3=both).
 */
function getEffectiveAccessMode() {
  const e = process.env.FOX_ACCESS_MODE;
  if (e === '1' || e === '2' || e === '3') return e;
  const saved = getSavedAccessMode();
  if (saved) return saved;
  return '2';
}

/**
 * First-run: choose how host publishes port 8787 / Tailscale caps.
 * Originally Windows-only (#issue-XX); macOS parity added for #96 so
 * DMG users can opt into Tailscale before container creation. No-op on
 * Linux (host-script users go through install.sh's chooser) and when
 * prefs already exist.
 *
 * @param {{ parent?: import('electron').BrowserWindow }} [opts]
 *   `parent` is the window the modal should attach to; without it on
 *   Windows the message box races other foreground claimants (e.g. the
 *   FITB progress window with `alwaysOnTop: true`) and ends up rendered
 *   behind them — #330. main.js / startup-orchestrator pass the active
 *   progress window through so the dialog is a proper modal child.
 */
async function ensureDockerAccessModeChosen(opts = {}) {
  if (process.platform !== 'win32' && process.platform !== 'darwin') return;
  if (getSavedAccessMode() !== null) return;
  const { dialog } = require('electron');
  const boxOpts = {
    type: 'question',
    title: 'Fox in the box — Where do you want to use Fox?',
    message: 'Where do you want to use Fox?',
    detail:
      'On this PC only — access Fox in your browser at localhost:8787.\n\n'
      + 'On this PC + phone/tablet/laptop — Tailscale connects your devices together so you can open Fox from anywhere on your personal network. Free, no subscription. Recommended.\n\n'
      + 'Both options — localhost AND Tailscale.\n\n'
      + 'To change later: remove the fox-in-the-box container in Docker Desktop and relaunch.',
    buttons: ['This PC only', 'This PC + other devices (Tailscale)', 'Both', 'Cancel'],
    defaultId: 1,
    cancelId: 3,
  };
  const { response } = opts.parent
    ? await dialog.showMessageBox(opts.parent, boxOpts)
    : await dialog.showMessageBox(boxOpts);
  if (response === 3) {
    const err = new Error('Setup cancelled at network access step.');
    err.code = 'ACCESS_MODE_CANCELLED';
    throw err;
  }
  const mode = response === 0 ? '1' : response === 1 ? '2' : '3';
  saveAccessMode(mode);
}

function buildContainerCreateOptions(dataDir, accessMode) {
  const hostConfig = {
    AutoRemove: true,
    // /app/workspace bind added in v0.7.9 (#145): the agent's
    // default_workspace is /app/workspace, which lived on the container's
    // writable layer and was wiped on every AutoRemove recreate. Map it
    // to a host directory next to dataDir so files survive Fox restarts.
    // The dataDir itself is already mapped to /data; workspace gets its
    // own mount so existing :stable users don't see their dataDir's tree
    // change shape.
    Binds: [`${dataDir}:/data`, `${dataDir}/workspace:/app/workspace`],
    PortBindings: {
      [PORT]: [
        {
          HostIp: accessMode === '1' || accessMode === '3' ? '0.0.0.0' : '127.0.0.1',
          HostPort: '8787',
        },
      ],
    },
    // Lets the container reach a host-side daemon at host.docker.internal —
    // required for the local-Ollama integration (issue #66) on Linux. Docker
    // Desktop on macOS/Windows resolves this name natively. Linux Docker
    // Engine 20.10+ takes the special host-gateway value as a placeholder
    // for the host's gateway address.
    ExtraHosts: ['host.docker.internal:host-gateway'],
  };
  if (accessMode === '2' || accessMode === '3') {
    hostConfig.CapAdd = ['NET_ADMIN'];
    hostConfig.Devices = [
      {
        PathOnHost: '/dev/net/tun',
        PathInContainer: '/dev/net/tun',
        CgroupPermissions: 'rwm',
      },
    ];
    hostConfig.Sysctls = { 'net.ipv4.ip_forward': '1' };
  }
  return {
    name: CNAME,
    Image: IMAGE,
    HostConfig: hostConfig,
    ExposedPorts: { [PORT]: {} },
  };
}

async function createAndStartContainer() {
  const dataDir = getDataDir();
  const accessMode = getEffectiveAccessMode();
  try {
    const container = await docker.createContainer(buildContainerCreateOptions(dataDir, accessMode));
    await container.start();
    log.info('Container started:', CNAME);
    return { container, reused: false, reason: 'created-new' };
  } catch (err) {
    if (err.statusCode === 409) {
      const existing = await getContainerByName({ all: true });
      if (existing) {
        const container = docker.getContainer(existing.Id);
        if (existing.State !== 'running') await container.start();
        log.warn('Recovered from container name conflict by reusing existing container');
        return { container, reused: true, reason: 'recovered-conflict' };
      }
    }
    throw dockerError('CONTAINER_CREATE_FAILED', `Failed to create container "${CNAME}"`, err);
  }
}

/**
 * Resolve the digest of the currently-tagged IMAGE on disk. Returns null if
 * the image isn't pulled locally (which means createAndStartContainer will
 * trigger a fresh create against whatever the upstream registry serves).
 */
async function _getCurrentImageId() {
  try {
    const inspect = await docker.getImage(IMAGE).inspect();
    return inspect && inspect.Id ? inspect.Id : null;
  } catch (err) {
    log.debug('Image inspect failed (probably not pulled):', err.message);
    return null;
  }
}

async function ensureContainerRunning() {
  const existing = await getContainerByName({ all: true });
  if (existing) {
    // v0.7.18 #340: if the existing container was created from a stale image
    // (older digest than what's currently tagged IMAGE), recreate it. Without
    // this check, upgrades publish a new container image but users keep
    // running the old container against the old image — the v0.7.17 Anthropic
    // fix shipped to :stable but @roadhero's machine stayed on v0.7.16 until
    // we manually `docker rm` + `docker rmi`'d it.
    //
    // Compare existing.ImageID (full sha256 of the image the container was
    // created from) against the current `IMAGE` tag's resolved digest. If
    // they differ → stop, remove, and fall through to createAndStartContainer.
    // The bind mounts on /data + /app/workspace preserve user data across
    // recreate; nothing else is lost.
    const currentImageId = await _getCurrentImageId();
    if (currentImageId && existing.ImageID && existing.ImageID !== currentImageId) {
      log.info(
        `Container image is stale (existing=${existing.ImageID.slice(0, 19)}…, ` +
        `current=${currentImageId.slice(0, 19)}…) — recreating against new image`,
      );
      const container = docker.getContainer(existing.Id);
      try {
        if (existing.State === 'running') {
          await container.stop({ t: 10 });
        }
        await container.remove({ force: true });
      } catch (err) {
        log.warn('Failed to remove stale container before recreate:', err.message);
      }
      const created = await createAndStartContainer();
      return { ...created, reason: 'recreated-after-image-upgrade' };
    }

    const container = docker.getContainer(existing.Id);
    if (existing.State === 'running') {
      log.info('Container already running:', CNAME);
      return { container, reused: true, reason: 'already-running' };
    }
    try {
      await container.start();
      log.info('Started existing container:', CNAME);
      return { container, reused: true, reason: 'started-existing' };
    } catch (err) {
      throw dockerError('CONTAINER_START_FAILED', `Failed to start existing container "${CNAME}"`, err);
    }
  }
  return createAndStartContainer();
}

/**
 * Stop the named container with a 10-second timeout.
 */
async function stopContainer() {
  const running = await getContainerByName({ all: false });
  if (!running) {
    log.info('stopContainer: container not running, nothing to stop');
    return;
  }
  const container = docker.getContainer(running.Id);
  await container.stop({ t: 10 });
  log.info('Container stopped:', CNAME);
}

/**
 * Restart the named container.
 */
async function restartContainer() {
  const running = await getContainerByName({ all: false });
  if (!running) throw dockerError('CONTAINER_NOT_RUNNING', 'Container not running');
  const container = docker.getContainer(running.Id);
  await container.restart({ t: 10 });
  log.info('Container restarted:', CNAME);
}

/**
 * v0.7.18 #341: complete docker-side teardown for the tray Reset Fox flow.
 *
 * Stops + force-removes the named container (if any), then untags the
 * `:stable` image so the next launch pulls a fresh manifest. Safe to call
 * when the container/image don't exist — each step swallows its own
 * "not found" failure independently so we make best effort across both.
 */
async function removeContainerAndImage() {
  if (!docker) return;
  // 1) Container
  try {
    const existing = await getContainerByName({ all: true });
    if (existing) {
      const container = docker.getContainer(existing.Id);
      try {
        if (existing.State === 'running') await container.stop({ t: 10 });
      } catch (err) {
        log.debug('removeContainerAndImage: stop failed:', err.message);
      }
      try {
        await container.remove({ force: true });
        log.info('removeContainerAndImage: container removed');
      } catch (err) {
        log.warn('removeContainerAndImage: container remove failed:', err.message);
      }
    }
  } catch (err) {
    log.warn('removeContainerAndImage: container lookup failed:', err.message);
  }
  // 2) Image
  try {
    await docker.getImage(IMAGE).remove({ force: true });
    log.info(`removeContainerAndImage: image ${IMAGE} removed`);
  } catch (err) {
    log.debug(`removeContainerAndImage: image remove failed (may not be pulled): ${err.message}`);
  }
}

async function getDiagnostics() {
  const diagnostics = {
    activeSocket,
    socketCandidates: socketCandidates.map((c) => c.socketPath || 'default'),
    daemonReachable: false,
    dockerVersion: null,
    container: null,
    containerLogs: null,
  };
  if (!docker) return diagnostics;

  try {
    diagnostics.daemonReachable = await isDaemonRunning();
    if (diagnostics.daemonReachable) {
      diagnostics.dockerVersion = await docker.version();
      const container = await getContainerByName({ all: true });
      if (container) {
        diagnostics.container = {
          id: container.Id,
          name: container.Names && container.Names[0],
          state: container.State,
          status: container.Status,
        };
        try {
          const rawLogs = await docker.getContainer(container.Id).logs({
            stdout: true,
            stderr: true,
            tail: 100,
          });
          diagnostics.containerLogs = rawLogs.toString('utf8').slice(-8000);
        } catch (err) {
          diagnostics.containerLogs = `Failed to fetch container logs: ${err.message}`;
        }
      }
    }
  } catch (err) {
    diagnostics.error = err.message;
  }
  return diagnostics;
}

function monitorContainerSetupLogs(showProgress, {
  pollIntervalMs = 1_000,
  tailLines = 400,
} = {}) {
  if (typeof showProgress !== 'function') return () => {};

  let stopped = false;
  let timer = null;
  const state = {
    currentApp: null,
    lastStatus: null,
  };

  const poll = async () => {
    if (stopped) return;
    try {
      const running = await getContainerByName({ all: true });
      if (!running) return;
      const container = docker.getContainer(running.Id);
      const raw = await container.logs({
        stdout: true,
        stderr: true,
        tail: tailLines,
      });

      const parsed = extractSetupStatusFromLogs(raw.toString('utf8'), state);
      state.currentApp = parsed.currentApp;
      // Race guard: container.logs() above is async and can return AFTER
      // stopLogMonitor() was called. Without this re-check, a late
      // showProgress() call after closeProgress() would create a fresh
      // launcher window stuck on step 5 (FITB #271).
      if (stopped) return;
      if (parsed.status && parsed.status !== state.lastStatus) {
        state.lastStatus = parsed.status;
        showProgress(parsed.status);
      }
    } catch (err) {
      log.debug('monitorContainerSetupLogs poll failed:', err.message);
    } finally {
      if (!stopped) timer = setTimeout(poll, pollIntervalMs);
    }
  };

  poll();

  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
  };
}

module.exports = {
  init,
  sanitizeLogText,
  extractSetupStatusFromLogs,
  monitorContainerSetupLogs,
  isDaemonRunning,
  getLastDaemonErrorCode,
  isImagePresent,
  pullImage,
  getRunningContainer,
  getContainerByName,
  ensureDockerAccessModeChosen,
  getSavedAccessMode,
  saveAccessMode,
  getEffectiveAccessMode,
  buildContainerCreateOptions,
  ensureContainerRunning,
  startContainer,
  stopContainer,
  restartContainer,
  removeContainerAndImage,
  getDiagnostics,
};
