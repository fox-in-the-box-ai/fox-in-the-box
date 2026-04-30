'use strict';

const Dockerode = require('dockerode');
const log = require('electron-log');

const IMAGE  = 'ghcr.io/fox-in-the-box-ai/cloud:stable';
const CNAME  = 'fox-in-the-box';
const PORT   = '8787/tcp';

let docker = null;

/** Initialise the Dockerode client (called once from main.js). */
function init() {
  docker = new Dockerode();
}

/**
 * Returns true if the Docker daemon is reachable.
 * Throws if Dockerode cannot be initialised.
 */
async function isDaemonRunning() {
  try {
    await docker.ping();
    return true;
  } catch (err) {
    log.warn('Docker daemon not reachable:', err.message);
    return false;
  }
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
      docker.modem.followProgress(stream, onFinish, onEvent);

      function onEvent(evt) {
        if (evt.progressDetail && evt.progressDetail.total) {
          const pct = Math.round(
            (evt.progressDetail.current / evt.progressDetail.total) * 100
          );
          onProgress(pct);
        }
      }
      function onFinish(err2) {
        if (err2) reject(err2);
        else resolve();
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

/**
 * Start the Fox container. Assumes image is already present.
 * Returns the container object.
 */
async function startContainer() {
  // Use Electron's app.getPath('userData') for the OS-native path:
  //   Windows: %APPDATA%\Fox in the Box
  //   macOS:   ~/Library/Application Support/Fox in the Box
  //   Linux:   ~/.config/Fox in the Box  (or FOX_DATA_DIR override)
  // Fall back to FOX_DATA_DIR env var, then ~/.foxinthebox for non-Electron contexts.
  let dataDir;
  try {
    const { app } = require('electron');
    dataDir = process.env.FOX_DATA_DIR || app.getPath('userData');
  } catch (_) {
    const os = require('os');
    const path = require('path');
    dataDir = process.env.FOX_DATA_DIR || path.join(os.homedir(), '.foxinthebox');
  }

  const container = await docker.createContainer({
    name: CNAME,
    Image: IMAGE,
    HostConfig: {
      AutoRemove: true,
      CapAdd: ['NET_ADMIN'],
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
  return container;
}

/**
 * Stop the named container with a 10-second timeout.
 */
async function stopContainer() {
  const containers = await docker.listContainers({
    filters: { name: [CNAME] },
  });
  if (containers.length === 0) {
    log.info('stopContainer: container not running, nothing to stop');
    return;
  }
  const container = docker.getContainer(containers[0].Id);
  await container.stop({ t: 10 });
  log.info('Container stopped:', CNAME);
}

/**
 * Restart the named container.
 */
async function restartContainer() {
  const containers = await docker.listContainers({
    filters: { name: [CNAME] },
  });
  if (containers.length === 0) throw new Error('Container not running');
  const container = docker.getContainer(containers[0].Id);
  await container.restart({ t: 10 });
  log.info('Container restarted:', CNAME);
}

module.exports = {
  init,
  isDaemonRunning,
  isImagePresent,
  pullImage,
  getRunningContainer,
  startContainer,
  stopContainer,
  restartContainer,
};
