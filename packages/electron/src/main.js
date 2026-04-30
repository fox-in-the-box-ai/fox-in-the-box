'use strict';

const { app, dialog } = require('electron');
const { exec }        = require('child_process');
const log             = require('electron-log');
const docker          = require('./docker-manager');
const { waitUntilHealthy } = require('./health-check');
const { createTray, setRunning } = require('./tray-manager');
const { shell }       = require('electron');

// Prevent multiple instances
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// Keep app alive when all windows are closed (tray-only)
app.on('window-all-closed', (e) => e.preventDefault());

app.whenReady().then(main).catch((err) => {
  log.error('Fatal startup error:', err);
  dialog.showErrorBox('Fox in the Box — startup error', err.message);
  app.quit();
});

// ─── Helpers ────────────────────────────────────────────────────────────────

function runCommand(cmd) {
  return new Promise((resolve, reject) => {
    exec(cmd, (error, stdout, stderr) => {
      if (error) reject(new Error(stderr || error.message));
      else resolve(stdout);
    });
  });
}

async function installDocker() {
  const platform = process.platform;
  const instruction =
    platform === 'win32'
      ? 'winget install Docker.DockerDesktop'
      : 'brew install --cask docker';

  const { response } = await dialog.showMessageBox({
    type: 'question',
    buttons: ['Install Docker', 'Cancel'],
    defaultId: 0,
    cancelId: 1,
    title: 'Docker not found',
    message: 'Docker Desktop is required but was not found.',
    detail: `Fox in the Box will run:\n\n  ${instruction}\n\nThis may take several minutes.`,
  });

  if (response !== 0) throw new Error('User cancelled Docker installation');

  log.info('Installing Docker:', instruction);
  await runCommand(instruction);
  log.info('Docker install command finished — waiting 5s for daemon');
  await new Promise((r) => setTimeout(r, 5000));
}

// ─── Main startup sequence ───────────────────────────────────────────────────

async function main() {
  log.info('Fox in the Box starting up');

  // 1. Initialise Docker client
  docker.init();

  // 2. Check Docker daemon
  let dockerRunning = await docker.isDaemonRunning();
  if (!dockerRunning) {
    await installDocker();
    dockerRunning = await docker.isDaemonRunning();
    if (!dockerRunning) {
      throw new Error(
        'Docker daemon still not reachable after install. ' +
        'Please start Docker Desktop manually and relaunch Fox in the Box.'
      );
    }
  }

  // 3. Pull image if not present
  if (!(await docker.isImagePresent())) {
    log.info('Image not found locally — pulling');
    await new Promise((resolve, reject) => {
      // Show a non-blocking info notice; dismiss automatically when done
      const notice = dialog.showMessageBox({
        type: 'info',
        buttons: [],
        title: 'Fox in the Box',
        message: 'Downloading Fox in the Box…',
        detail: 'This only happens once. Please wait.',
      });
      docker.pullImage((pct) => log.info(`Pull progress: ${pct}%`))
        .then(() => { resolve(); })
        .catch(reject);
    });
    log.info('Image pull complete');
  }

  // 4. Start container if not already running
  const running = await docker.getRunningContainer();
  if (!running) {
    log.info('Container not running — starting');
    await docker.startContainer();
  } else {
    log.info('Container already running');
  }

  // 5. Wait for health
  log.info('Waiting for container to become healthy');
  await waitUntilHealthy();

  // 6. Open browser
  log.info('Opening browser at http://localhost:8787');
  await shell.openExternal('http://localhost:8787');

  // 7. Create tray icon
  createTray(true);
  setRunning(true);
}
