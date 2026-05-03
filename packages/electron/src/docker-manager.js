'use strict';

const Dockerode = require('dockerode');
const log = require('electron-log');
const fs = require('fs');
const os = require('os');
const path = require('path');

const IMAGE  = 'ghcr.io/fox-in-the-box-ai/cloud:stable';
const CNAME  = 'fox-in-the-box';
const PORT   = '8787/tcp';

let docker = null;
let activeSocket = 'default';
let socketCandidates = [{}];

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
 */
async function isDaemonRunning() {
  if (!docker) throw dockerError('DOCKER_NOT_INITIALIZED', 'Docker manager not initialized');
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
  return false;
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

async function createAndStartContainer() {
  const dataDir = getDataDir();
  try {
    const container = await docker.createContainer({
      name: CNAME,
      Image: IMAGE,
      HostConfig: {
        AutoRemove: true,
        CapAdd: ['NET_ADMIN'],
        Devices: [
          {
            PathOnHost: '/dev/net/tun',
            PathInContainer: '/dev/net/tun',
            CgroupPermissions: 'rwm',
          },
        ],
        Sysctls: { 'net.ipv4.ip_forward': '1' },
        PortBindings: {
          [PORT]: [{ HostIp: '127.0.0.1', HostPort: '8787' }],
        },
        Binds: [`${dataDir}:/data`],
      },
      ExposedPorts: { [PORT]: {} },
    });
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

async function ensureContainerRunning() {
  const existing = await getContainerByName({ all: true });
  if (existing) {
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
  pollIntervalMs = 1500,
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
  isImagePresent,
  pullImage,
  getRunningContainer,
  getContainerByName,
  ensureContainerRunning,
  startContainer,
  stopContainer,
  restartContainer,
  getDiagnostics,
};
