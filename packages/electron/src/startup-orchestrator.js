'use strict';

const crypto = require('crypto');
const log = require('electron-log');
const STEP_ORDER = [
  'preflight',
  'docker_daemon_ready',
  'image_ready',
  'container_ready',
  'http_healthy',
  'onboarding_opened',
];
const STEP_LABELS = {
  preflight: 'Initialize app',
  docker_daemon_ready: 'Prepare Docker daemon',
  image_ready: 'Ensure container image',
  container_ready: 'Prepare container',
  http_healthy: 'Wait for services',
  onboarding_opened: 'Open setup wizard',
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
  platform = process.platform,
}) {
  const sessionId = crypto.randomUUID();
  const preflightProgress = createPhaseProgress(showProgress, 'preflight');
  const daemonProgress = createPhaseProgress(showProgress, 'docker_daemon_ready');
  const imageProgress = createPhaseProgress(showProgress, 'image_ready');
  const containerProgress = createPhaseProgress(showProgress, 'container_ready');
  const healthProgress = createPhaseProgress(showProgress, 'http_healthy');

  await runPhase(sessionId, 'preflight', async () => {
    preflightProgress('Preparing desktop runtime…');
    docker.init();
  });

  const daemonPhaseResult = await runPhase(sessionId, 'docker_daemon_ready', async () => {
    let dockerRunning = await docker.isDaemonRunning();
    if (dockerRunning) return;

    if (platform === 'win32') {
      daemonProgress('Setting up Docker…');
      const winDocker = await ensureDockerWindows(daemonProgress);
      if (winDocker && winDocker.result === 'reboot-required') {
        if (closeProgress) closeProgress();
        return { outcome: 'reboot-required' };
      }
      dockerRunning = await docker.isDaemonRunning();
    } else if (platform === 'darwin') {
      daemonProgress('Setting up Docker…');
      await installDockerMac(daemonProgress);
      dockerRunning = await waitForDaemon(180_000, daemonProgress);
    } else {
      throw Object.assign(new Error('Unsupported desktop platform for one-click setup'), {
        code: 'UNSUPPORTED_PLATFORM',
      });
    }

    if (!dockerRunning) {
      if (onDaemonNotReady) await onDaemonNotReady({ platform });
      throw Object.assign(new Error('Docker daemon is still unavailable after setup'), {
        code: 'DAEMON_NOT_READY',
      });
    }
  });

  if (daemonPhaseResult && daemonPhaseResult.outcome === 'reboot-required') {
    return { sessionId, outcome: 'reboot-required' };
  }

  await runPhase(sessionId, 'image_ready', async () => {
    const present = await docker.isImagePresent();
    if (present) return;

    imageProgress('Downloading Fox in the box… (this only happens once)');
    await withTimeout(
      docker.pullImage((pct) => {
        imageProgress(`Downloading Fox in the box… ${pct}%`);
      }),
      15 * 60 * 1000,
      () => Object.assign(new Error('Image pull timed out'), { code: 'IMAGE_PULL_TIMEOUT' })
    );
  });

  await runPhase(sessionId, 'container_ready', async () => {
    containerProgress('Preparing Fox in the box container…');
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

  await runPhase(sessionId, 'http_healthy', async () => {
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

  if (closeProgress) closeProgress();

  await runPhase(sessionId, 'onboarding_opened', async () => {
    await openOnboarding();
  });

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
