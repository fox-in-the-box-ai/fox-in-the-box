'use strict';

/**
 * startup.js — testable startup logic extracted from main.js
 *
 * All functions here are pure or take their dependencies as arguments,
 * so they can be unit-tested without Electron or a real Docker daemon.
 */

const { exec, spawn } = require('child_process');
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
 * Poll until the Docker daemon responds, up to timeoutMs.
 * Returns true if daemon came up, false on timeout.
 *
 * @param {Function} isDaemonRunning - injectable for testing
 * @param {number}   timeoutMs
 * @param {number}   intervalMs
 * @param {Function} [_now]   - injectable clock (Date.now) for testing
 * @param {Function} [_sleep] - injectable sleep for testing
 */
async function waitForDaemon(
  isDaemonRunning,
  timeoutMs = 120_000,
  intervalMs = 3_000,
  _now   = () => Date.now(),
  _sleep = (ms) => new Promise((r) => setTimeout(r, ms))
) {
  const deadline = _now() + timeoutMs;
  while (_now() < deadline) {
    if (await isDaemonRunning()) return true;
    await _sleep(intervalMs);
  }
  return false;
}

/**
 * Find Docker Desktop exe path, or 'service' for Mirantis Engine, or null.
 * @param {Function} [_run] - injectable runCommand for testing
 */
async function findDockerDesktopExe(_run = runCommand) {
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
    showProgress(state.action === 'service' ? 'Starting Docker Engine…' : 'Starting Docker Desktop…');
    if (state.action === 'start-service') {
      await _run('net start com.docker.service', { shell: true }).catch(() => {});
    } else {
      spawnDetached(state.exe);
    }
    const came_up = await _waitForDaemon();
    if (came_up) return { result: 'started' };
    showRebootRequired();
    return { result: 'reboot-required' };
  }

  // action === 'install'
  showProgress('Docker not found — installing Docker Desktop…');
  await _run(
    'winget install --id Docker.DockerDesktop --silent --accept-source-agreements --accept-package-agreements',
    { shell: true, timeout: 300_000 }
  ).catch((err) => {
    // winget exits non-zero when already installed — not an error
    if (err.message && (
      err.message.includes('already installed') ||
      err.message.includes('No applicable upgrade') ||
      err.message.includes('0x8A150101')
    )) return;
    throw new Error(
      'Could not install Docker Desktop automatically.\n\n' +
      'Please install it manually from https://docker.com/products/docker-desktop,\n' +
      'then reopen Fox in the Box.'
    );
  });

  showProgress('Waiting for Docker to start…');
  const ready = await _waitForDaemon();
  if (!ready) {
    showRebootRequired();
    return { result: 'reboot-required' };
  }
  return { result: 'installed' };
}

module.exports = {
  runCommand,
  waitForDaemon,
  findDockerDesktopExe,
  detectWindowsDockerState,
  ensureDockerWindows,
};
