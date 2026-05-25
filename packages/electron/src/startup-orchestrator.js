'use strict';

const crypto = require('crypto');
const log = require('electron-log');
const STEP_ORDER = [
  'check_system',
  'docker_install',
  'docker_start',
  'download_image',
  'start_container',
  'wait_services',
  'connect_network',
];
const STEP_LABELS = {
  check_system: 'Check system',
  docker_install: 'Install Docker',
  docker_start: 'Start Docker',
  download_image: 'Download image',
  start_container: 'Start container',
  wait_services: 'Wait for services',
  connect_network: 'Connect network',
};

class StartupPhaseError extends Error {
  constructor(phase, message, details = {}) {
    super(message);
    this.name = 'StartupPhaseError';
    this.phase = phase;
    this.code = details.code || 'STARTUP_PHASE_FAILED';
    this.details = details;
    this.cause = details.cause || null;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function withTimeout(promise, timeoutMs, onTimeout) {
  let timer = null;
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(onTimeout()), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function logPhase(sessionId, phase, status, payload = {}) {
  log.info('[startup-phase]', JSON.stringify({
    sessionId,
    phase,
    status,
    ts: new Date().toISOString(),
    ...payload,
  }));
}

function createPhaseProgress(showProgress, phase) {
  if (typeof showProgress !== 'function') return () => {};
  const idx = STEP_ORDER.indexOf(phase);
  const step = idx >= 0 ? idx + 1 : 1;
  const total = STEP_ORDER.length;
  const label = STEP_LABELS[phase] || phase;
  return (message) => showProgress(`Step ${step}/${total} - ${label}: ${message}`);
}

async function runPhase(sessionId, phase, action) {
  const startedAt = Date.now();
  logPhase(sessionId, phase, 'start');
  try {
    const result = await action();
    logPhase(sessionId, phase, 'ok', { durationMs: Date.now() - startedAt });
    return result;
  } catch (err) {
    logPhase(sessionId, phase, 'error', {
      durationMs: Date.now() - startedAt,
      errorCode: err.code || 'UNSPECIFIED',
      errorMessage: err.message,
    });
    throw new StartupPhaseError(phase, err.message, {
      code: err.code || 'UNSPECIFIED',
      cause: err,
      sessionId,
    });
  }
}

async function runStartup({
  docker,
  waitUntilHealthy,
  ensureDockerWindows,
  installDockerMac,
  waitForDaemon,
  showProgress,
  closeProgress,
  openOnboarding,
  onDaemonNotReady,
  pollTailscaleUrl = null,
  getDialogParent = () => null,
  platform = process.platform,
}) {
  const sessionId = crypto.randomUUID();
  const checkProgress = createPhaseProgress(showProgress, 'check_system');
  const installProgress = createPhaseProgress(showProgress, 'docker_install');
  const startProgress = createPhaseProgress(showProgress, 'docker_start');
  const imageProgress = createPhaseProgress(showProgress, 'download_image');
  const containerProgress = createPhaseProgress(showProgress, 'start_container');
  const healthProgress = createPhaseProgress(showProgress, 'wait_services');
  const networkProgress = createPhaseProgress(showProgress, 'connect_network');

  let daemonWasRunning = false;

  await runPhase(sessionId, 'check_system', async () => {
    checkProgress('Preparing desktop runtime…');
    docker.init();
    daemonWasRunning = await docker.isDaemonRunning();

    if (!daemonWasRunning) {
      const daemonErrCode = docker.getLastDaemonErrorCode && docker.getLastDaemonErrorCode();
      if (daemonErrCode === 'DOCKER_WINDOWS_CONTAINERS_MODE') {
        throw Object.assign(
          new Error(
            'Docker Desktop is running in Windows-containers mode. Fox needs Linux containers.',
          ),
          { code: 'DOCKER_WINDOWS_CONTAINERS_MODE', nonRecoverable: true },
        );
      }
    }
  });

  const installResult = await runPhase(sessionId, 'docker_install', async () => {
    if (daemonWasRunning) return;

    if (platform === 'win32') {
      installProgress('Installing Docker Desktop…');
      const winDocker = await ensureDockerWindows(installProgress);
      if (winDocker && winDocker.result === 'reboot-required') {
        if (closeProgress) closeProgress();
        return { outcome: 'reboot-required' };
      }
    } else if (platform === 'darwin') {
      installProgress('Installing Docker Desktop…');
      await installDockerMac(installProgress);
    } else {
      throw Object.assign(new Error('Unsupported desktop platform for one-click setup'), {
        code: 'UNSUPPORTED_PLATFORM',
      });
    }
  });

  if (installResult && installResult.outcome === 'reboot-required') {
    return { sessionId, outcome: 'reboot-required' };
  }

  await runPhase(sessionId, 'docker_start', async () => {
    if (daemonWasRunning) return;

    startProgress('Waiting for Docker daemon…');
    const dockerRunning = await waitForDaemon(180_000, startProgress);

    if (!dockerRunning) {
      if (onDaemonNotReady) await onDaemonNotReady({ platform });
      throw Object.assign(new Error('Docker daemon is still unavailable after setup'), {
        code: 'DAEMON_NOT_READY',
      });
    }
  });

  await runPhase(sessionId, 'download_image', async () => {
    imageProgress('Checking for updates and preparing container image…');
    await withTimeout(
      docker.pullImage((pct) => {
        imageProgress(`Preparing container image… ${pct}%`);
      }),
      15 * 60 * 1000,
      () => Object.assign(new Error('Image pull timed out'), { code: 'IMAGE_PULL_TIMEOUT' })
    );
  });

  await runPhase(sessionId, 'start_container', async () => {
    containerProgress('Preparing Fox in the box container…');
    if (typeof docker.ensureDockerAccessModeChosen === 'function') {
      await docker.ensureDockerAccessModeChosen({ parent: getDialogParent() });
    }
    const result = await docker.ensureContainerRunning();
    if (!result || !result.reason) return;
    if (result.reason === 'already-running') {
      containerProgress('Container already running. Reusing existing instance…');
      return;
    }
    if (result.reason === 'started-existing') {
      containerProgress('Started existing container instance…');
      return;
    }
    if (result.reason === 'recovered-conflict') {
      containerProgress('Recovered from container naming conflict. Continuing…');
      return;
    }
    containerProgress('Created and started a new container instance…');
  });

  await runPhase(sessionId, 'wait_services', async () => {
    const stopLogMonitor = typeof docker.monitorContainerSetupLogs === 'function'
      ? docker.monitorContainerSetupLogs(healthProgress)
      : null;
    try {
      await waitUntilHealthy({
        timeoutMs: 120_000,
        intervalMs: 500,
        requestTimeoutMs: 1500,
        showProgress: healthProgress,
        failFastCheck: async ({ attempts }) => {
          if (attempts % 5 !== 0) return null;
          const daemonUp = await docker.isDaemonRunning();
          if (!daemonUp) {
            const err = new Error('Docker daemon became unavailable while waiting for services.');
            err.code = 'DAEMON_LOST_DURING_HEALTH';
            return err;
          }
          const container = await docker.getContainerByName({ all: true });
          if (!container) {
            const err = new Error('Container disappeared while waiting for services.');
            err.code = 'CONTAINER_MISSING_DURING_HEALTH';
            return err;
          }
          if (container.State && container.State !== 'running') {
            const err = new Error(`Container state changed to "${container.State}" while waiting for services.`);
            err.code = 'CONTAINER_NOT_RUNNING_DURING_HEALTH';
            err.meta = { containerState: container.State };
            return err;
          }
          return null;
        },
      });
    } finally {
      if (stopLogMonitor) stopLogMonitor();
    }
  });

  await runPhase(sessionId, 'connect_network', async () => {
    if (pollTailscaleUrl) {
      networkProgress('Connecting to network…');
      await pollTailscaleUrl(networkProgress);
    }
  });

  if (closeProgress) closeProgress();
  await openOnboarding();

  return { sessionId };
}

async function ensureContainerHealthy({
  docker,
  waitUntilHealthy,
  showProgress = null,
  openOnboarding = null,
}) {
  const containerProgress = typeof showProgress === 'function'
    ? (msg) => showProgress(`Step 1/2 - Prepare container: ${msg}`)
    : null;
  const healthProgress = typeof showProgress === 'function'
    ? (msg) => showProgress(`Step 2/2 - Wait for services: ${msg}`)
    : null;
  const stopLogMonitor = typeof docker.monitorContainerSetupLogs === 'function'
    ? docker.monitorContainerSetupLogs(healthProgress || showProgress)
    : null;
  const result = await docker.ensureContainerRunning();
  if (containerProgress && result && result.reason) {
    if (result.reason === 'already-running') {
      containerProgress('Container already running. Reusing existing instance…');
    } else if (result.reason === 'started-existing') {
      containerProgress('Started existing container instance…');
    } else if (result.reason === 'recovered-conflict') {
      containerProgress('Recovered from container naming conflict. Continuing…');
    } else {
      containerProgress('Created and started a new container instance…');
    }
  }
  try {
    await waitUntilHealthy({
      timeoutMs: 120_000,
      intervalMs: 500,
      requestTimeoutMs: 1500,
      showProgress: healthProgress || showProgress,
      failFastCheck: async ({ attempts }) => {
        if (attempts % 5 !== 0) return null;
        const daemonUp = await docker.isDaemonRunning();
        if (!daemonUp) {
          const err = new Error('Docker daemon became unavailable while waiting for services.');
          err.code = 'DAEMON_LOST_DURING_HEALTH';
          return err;
        }
        const container = await docker.getContainerByName({ all: true });
        if (!container) {
          const err = new Error('Container disappeared while waiting for services.');
          err.code = 'CONTAINER_MISSING_DURING_HEALTH';
          return err;
        }
        if (container.State && container.State !== 'running') {
          const err = new Error(`Container state changed to "${container.State}" while waiting for services.`);
          err.code = 'CONTAINER_NOT_RUNNING_DURING_HEALTH';
          err.meta = { containerState: container.State };
          return err;
        }
        return null;
      },
    });
  } finally {
    if (stopLogMonitor) stopLogMonitor();
  }
  if (openOnboarding) await openOnboarding();
}

module.exports = {
  StartupPhaseError,
  sleep,
  runStartup,
  ensureContainerHealthy,
};
