'use strict';

/**
 * startup.js — testable startup logic extracted from main.js
 *
 * All functions here are pure or take their dependencies as arguments,
 * so they can be unit-tested without Electron or a real Docker daemon.
 */

const { exec, execFile, spawn } = require('child_process');
const log = require('electron-log');

// ─── Helpers ─────────────────────────────────────────────────────────────────

function runCommand(cmd, opts = {}) {
  return new Promise((resolve, reject) => {
    exec(cmd, opts, (error, stdout, stderr) => {
      if (error) reject(new Error(stderr || error.message));
      else resolve(stdout);
    });
  });
}

/**
 * Run a command and stream stdout/stderr lines to showProgress.
 * Resolves with full stdout, rejects on non-zero exit.
 */
function runCommandVerbose(cmd, opts = {}, showProgress = null) {
  return new Promise((resolve, reject) => {
    const child = exec(cmd, { ...opts, windowsHide: true });
    let stdout = '';
    let lastLine = '';

    const onData = (data) => {
      stdout += data;
      const lines = data.toString().split(/\r?\n/).filter(l => l.trim());
      if (lines.length && showProgress) {
        lastLine = lines[lines.length - 1].trim();
        // Trim winget progress bars and long lines
        const display = lastLine.replace(/[█▌▐▓░]+/g, '').trim().slice(0, 80);
        if (display) showProgress(display);
      }
    };

    child.stdout && child.stdout.on('data', onData);
    child.stderr && child.stderr.on('data', onData);

    child.on('close', (code) => {
      if (code !== 0) reject(new Error(lastLine || `exited with code ${code}`));
      else resolve(stdout);
    });
  });
}

/**
 * Poll until the Docker daemon responds, up to timeoutMs.
 * Returns true if daemon came up, false on timeout.
 *
 * @param {Function} isDaemonRunning - injectable for testing
 * @param {number}   timeoutMs
 * @param {number}   intervalMs
 * @param {Function} [_now]         - injectable clock (Date.now) for testing
 * @param {Function} [_sleep]       - injectable sleep for testing
 * @param {Function} [showProgress] - optional progress callback for elapsed time
 */
async function waitForDaemon(
  isDaemonRunning,
  timeoutMs = 120_000,
  intervalMs = 3_000,
  _now   = () => Date.now(),
  _sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  showProgress = null
) {
  const deadline = _now() + timeoutMs;
  const start = _now();
  while (_now() < deadline) {
    if (await isDaemonRunning()) return true;
    const elapsed = Math.round((_now() - start) / 1000);
    if (showProgress) showProgress(`Starting Docker Desktop… ${elapsed}s`);
    await _sleep(intervalMs);
  }
  return false;
}

/**
 * Check if Docker Desktop process is actually running.
 * Returns true/false. Used to detect silent spawn failures early.
 */
async function isDockerDesktopProcessRunning(_run = runCommand) {
  try {
    const out = await _run('tasklist /FI "IMAGENAME eq Docker Desktop.exe" /NH', { shell: true });
    return out.includes('Docker Desktop.exe');
  } catch (_) {
    return false;
  }
}

/**
 * Find Docker Desktop exe path, or 'service' for Mirantis Engine, or null.
 * @param {Function} [_run] - injectable runCommand for testing
 */
async function findDockerDesktopExe(_run = runCommand) {
  // Check registry for Docker Desktop install path — most reliable
  try {
    const out = await _run(
      'reg query "HKLM\\SOFTWARE\\Docker Inc.\\Docker Desktop" /v "InstallPath"',
      { shell: true }
    );
    const match = out.match(/InstallPath\s+REG_SZ\s+(.+)/);
    if (match) {
      const exePath = match[1].trim() + '\\Docker Desktop.exe';
      return exePath;
    }
  } catch (_) {}

  // Fallback: known install paths
  const candidates = [
    '%PROGRAMFILES%\\Docker\\Docker\\Docker Desktop.exe',
    '%LOCALAPPDATA%\\Programs\\Docker\\Docker\\Docker Desktop.exe',
  ];
  for (const c of candidates) {
    try {
      await _run(`if exist "${c}" (exit 0) else (exit 1)`, { shell: true });
      return c;
    } catch (_) { /* not here */ }
  }

  // Check if docker CLI is in PATH — means Desktop is installed somewhere
  try {
    const dockerPath = (await _run('where docker', { shell: true })).trim().split('\n')[0];
    // Derive Desktop exe: docker.exe is usually in <install>\resources\bin\docker.exe
    const derived = dockerPath.replace(/\\resources\\bin\\docker\.exe$/i, '\\Docker Desktop.exe');
    if (derived !== dockerPath) return derived;
    return 'cli-in-path'; // fallback if path doesn't match pattern
  } catch (_) {}

  // Check for Mirantis Docker Engine (Windows service)
  try {
    await _run('sc query com.docker.service', { shell: true });
    return 'service';
  } catch (_) {}

  return null;
}
/**
 * Determine what Windows Docker setup action is needed.
 *
 * Returns one of:
 *   { action: 'none' }              — daemon already running
 *   { action: 'start', exe }        — Desktop found, needs starting
 *   { action: 'start-service' }     — Mirantis Engine found, needs starting
 *   { action: 'install' }           — nothing found, needs install
 *
 * @param {Function} isDaemonRunning
 * @param {Function} [_findExe]
 */
async function detectWindowsDockerState(isDaemonRunning, _findExe = findDockerDesktopExe) {
  if (await isDaemonRunning()) return { action: 'none' };
  const exe = await _findExe();
  if (!exe)              return { action: 'install' };
  if (exe === 'service') return { action: 'start-service' };
  if (exe === 'cli-in-path') return { action: 'start', exe: null }; // Docker in PATH, start via service
  return { action: 'start', exe };
}

/**
 * Full Windows Docker setup flow.
 *
 * @param {Object} deps - injectable dependencies
 * @param {Function} deps.isDaemonRunning
 * @param {Function} deps.waitForDaemon     - pre-bound waitForDaemon(isDaemonRunning, ...)
 * @param {Function} deps.runCommand
 * @param {Function} deps.spawnDetached     - (exe) => void
 * @param {Function} deps.showProgress
 * @param {Function} deps.showRebootRequired
 * @param {Function} [deps._findExe]
 */
async function ensureDockerWindows(deps) {
  const {
    isDaemonRunning,
    waitForDaemon: _waitForDaemon,
    runCommand: _run,
    spawnDetached,
    showProgress,
    showRebootRequired,
    _findExe,
  } = deps;

  const state = await detectWindowsDockerState(isDaemonRunning, _findExe);

  if (state.action === 'none') return { result: 'already-running' };

  if (state.action === 'start' || state.action === 'start-service') {
    showProgress('Starting Docker Desktop… this can take up to 3 minutes on first launch.');
    if (state.action === 'start-service') {
      await _run('net start com.docker.service', { shell: true }).catch(() => {});
    } else if (state.exe) {
      spawnDetached(state.exe);
    } else {
      await _run('start "" "Docker Desktop"', { shell: true }).catch(() => {});
    }
    const came_up = await _waitForDaemon(180_000, showProgress);
    if (came_up) return { result: 'started' };
    showRebootRequired();
    return { result: 'reboot-required' };
  }

  // action === 'install'
  showProgress('Docker not found — installing Docker Desktop…');
  await _run(
    'winget install --id Docker.DockerDesktop --silent --accept-source-agreements --accept-package-agreements',
    { shell: true, timeout: 300_000 },
  ).catch((err) => {
    // winget exits non-zero when already installed — not an error
    if (err.message && (
      err.message.includes('already installed') ||
      err.message.includes('No applicable upgrade') ||
      err.message.includes('0x8A150101')
    )) return;
    const msg =
      'Could not install Docker Desktop automatically.\n\n' +
      'Please install it manually from https://docker.com/products/docker-desktop,\n' +
      'then reopen Fox in the Box.';
    if (deps.showError) { deps.showError(msg); return; }
    throw new Error(msg);
  });

  // Docker Desktop always requires a reboot after fresh install on Windows.
  // No point polling — show the reboot screen immediately.
  showRebootRequired();
  return { result: 'reboot-required' };
}

module.exports = {
  runCommand,
  runCommandVerbose,
  waitForDaemon,
  findDockerDesktopExe,
  detectWindowsDockerState,
  ensureDockerWindows,
};
