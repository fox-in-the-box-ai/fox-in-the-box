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
  intervalMs = 1_000,
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
  } catch (err) {
    log.debug('Docker Desktop process check failed:', err.message);
    return false;
  }
}

async function waitForDesktopProcessStart(
  isRunning,
  timeoutMs = 25_000,
  intervalMs = 500,
  _sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  showProgress = null
) {
  const startedAt = Date.now();
  while ((Date.now() - startedAt) < timeoutMs) {
    if (await isRunning()) return true;
    if (showProgress) {
      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      showProgress(`Launching Docker Desktop… ${elapsed}s`);
    }
    await _sleep(intervalMs);
  }
  return false;
}

async function diagnoseWindowsDocker(_run = runCommand) {
  const diagnostics = {
    issueCode: 'UNKNOWN',
    message: 'Docker daemon did not become available.',
    desktopProcessRunning: false,
    serviceExists: false,
    serviceRunning: false,
    wslStatus: null,
    wslList: null,
    dockerContext: null,
    errors: [],
  };

  try {
    diagnostics.desktopProcessRunning = await isDockerDesktopProcessRunning(_run);
  } catch (err) {
    diagnostics.errors.push(`desktop-process-check: ${err.message}`);
  }

  try {
    const out = await _run('sc query com.docker.service', { shell: true });
    diagnostics.serviceExists = true;
    diagnostics.serviceRunning = /STATE\s*:\s*\d+\s+RUNNING/i.test(out);
  } catch (_) {
    diagnostics.serviceExists = false;
  }

  try {
    diagnostics.wslStatus = await _run('wsl --status', { shell: true });
  } catch (err) {
    diagnostics.errors.push(`wsl-status: ${err.message}`);
  }

  let wslListRaw = null;
  try {
    wslListRaw = await _run('wsl -l -v', { shell: true });
  } catch (err) {
    diagnostics.errors.push(`wsl-list: ${err.message}`);
  }

  try {
    diagnostics.dockerContext = (await _run('docker context show', { shell: true })).trim();
  } catch (err) {
    diagnostics.errors.push(`docker-context: ${err.message}`);
  }

  // Docker Desktop registers docker-desktop / docker-desktop-data shortly after the
  // process starts; `wsl -l -v` can omit them for a few seconds and falsely trigger
  // WSL_BACKEND_MISSING while the Linux engine is already coming up.
  let wslList = (wslListRaw || '').trim();
  if (diagnostics.desktopProcessRunning && wslList && !/no installed distributions/i.test(wslList)) {
    let retries = 0;
    while (retries < 6 && !/docker-desktop/i.test(wslList)) {
      await new Promise((r) => setTimeout(r, 1_000));
      retries++;
      try {
        wslListRaw = await _run('wsl -l -v', { shell: true });
        wslList = (wslListRaw || '').trim();
      } catch (err) {
        diagnostics.errors.push(`wsl-list-retry-${retries}: ${err.message}`);
        break;
      }
    }
  }
  diagnostics.wslList = wslListRaw;

  if (/no installed distributions/i.test(wslList)) {
    diagnostics.issueCode = 'WSL_NOT_INITIALIZED';
    diagnostics.message = 'WSL backend is not initialized (no installed distributions).';
    return diagnostics;
  }
  // Ignore too-short output (transient / encoding glitches) — fall through to generic daemon wait.
  if (wslList.length >= 12 && !/docker-desktop/i.test(wslList)) {
    diagnostics.issueCode = 'WSL_BACKEND_MISSING';
    diagnostics.message = 'Docker Desktop WSL backend distro is missing.';
    return diagnostics;
  }
  if (!diagnostics.desktopProcessRunning) {
    diagnostics.issueCode = 'DOCKER_DESKTOP_NOT_RUNNING';
    diagnostics.message = 'Docker Desktop process is not running.';
    return diagnostics;
  }
  diagnostics.issueCode = 'DAEMON_NOT_READY';
  diagnostics.message = 'Docker Desktop is running but daemon pipe is unavailable.';
  return diagnostics;
}

async function attemptRecoverWindowsDocker(_run = runCommand, showProgress = null) {
  const recovery = {
    attempted: false,
    rebootRecommended: false,
    steps: [],
    errors: [],
  };
  const steps = [
    {
      label: 'Launch Docker Desktop',
      cmd: 'start "" /min "Docker Desktop"',
      opts: { shell: true, timeout: 30_000 },
    },
    {
      label: 'Install WSL platform components',
      cmd: 'wsl --install --no-distribution',
      opts: { shell: true, timeout: 180_000 },
    },
    {
      label: 'Update WSL kernel',
      cmd: 'wsl --update',
      opts: { shell: true, timeout: 120_000 },
    },
    {
      label: 'Enable WSL feature',
      cmd: 'dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart',
      opts: { shell: true, timeout: 180_000 },
    },
    {
      label: 'Enable virtual machine platform',
      cmd: 'dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart',
      opts: { shell: true, timeout: 180_000 },
    },
    {
      label: 'Set WSL default version to 2',
      cmd: 'wsl --set-default-version 2',
      opts: { shell: true, timeout: 60_000 },
    },
  ];

  for (const step of steps) {
    try {
      if (showProgress) showProgress(`${step.label}…`);
      await _run(step.cmd, step.opts);
      recovery.attempted = true;
      recovery.steps.push(step.label);
    } catch (err) {
      recovery.errors.push(`${step.label}: ${err.message}`);
      log.warn(`[startup-recovery] ${step.label} failed:`, err.message);
    }
  }

  // Give Docker Desktop time to provision docker-desktop WSL backend.
  const waitForBackend = async (timeoutMs = 90_000, intervalMs = 2_000) => {
    const startedAt = Date.now();
    while ((Date.now() - startedAt) < timeoutMs) {
      try {
        const out = await _run('wsl -l -v', { shell: true, timeout: 30_000 });
        if (/docker-desktop/i.test(out)) return true;
      } catch (_) {
        // ignore transient WSL command failures
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    return false;
  };

  let backendReady = await waitForBackend(45_000, 1_500);

  // If still missing, attempt one elevated "all-in-one" repair (single UAC prompt).
  if (!backendReady) {
    const elevatedRepair = `powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -Verb RunAs -Wait -ArgumentList '/c dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart && dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart && wsl --install --no-distribution && wsl --update && wsl --set-default-version 2'"`;
    try {
      if (showProgress) {
        showProgress(
          'Requesting administrator permission for WSL repair… After UAC, DISM/WSL can take several minutes with no further output.',
        );
      }
      const repairStartedAt = Date.now();
      let heartbeat = null;
      if (showProgress) {
        heartbeat = setInterval(() => {
          const sec = Math.round((Date.now() - repairStartedAt) / 1000);
          showProgress(`WSL repair still running (elevated DISM/WSL)… ${sec}s`);
        }, 20_000);
      }
      try {
        await _run(elevatedRepair, { shell: true, timeout: 10 * 60 * 1000 });
      } finally {
        if (heartbeat) clearInterval(heartbeat);
      }
      recovery.attempted = true;
      recovery.steps.push('Elevated WSL repair');
      backendReady = await waitForBackend(90_000, 2_000);
    } catch (err) {
      recovery.errors.push(`Elevated WSL repair: ${err.message}`);
      log.warn('[startup-recovery] Elevated WSL repair failed:', err.message);
    }
  }

  recovery.backendReady = backendReady;
  recovery.rebootRecommended = recovery.attempted && !backendReady;
  return recovery;
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
  } catch (err) {
    log.debug('Registry lookup for Docker Desktop failed:', err.message);
  }

  // Fallback: known install paths
  const candidates = [
    '%PROGRAMFILES%\\Docker\\Docker\\Docker Desktop.exe',
    '%LOCALAPPDATA%\\Programs\\Docker\\Docker\\Docker Desktop.exe',
  ];
  for (const c of candidates) {
    try {
      await _run(`if exist "${c}" (exit 0) else (exit 1)`, { shell: true });
      return c;
    } catch (err) {
      log.debug(`Docker candidate path not found: ${c}`, err.message);
    }
  }

  // Check if docker CLI is in PATH — means Desktop is installed somewhere
  try {
    const dockerPath = (await _run('where docker', { shell: true })).trim().split('\n')[0];
    // Derive Desktop exe: docker.exe is usually in <install>\resources\bin\docker.exe
    const derived = dockerPath.replace(/\\resources\\bin\\docker\.exe$/i, '\\Docker Desktop.exe');
    if (derived !== dockerPath) return derived;
    return 'cli-in-path'; // fallback if path doesn't match pattern
  } catch (err) {
    log.debug('Docker CLI path lookup failed:', err.message);
  }

  // Check for Mirantis Docker Engine (Windows service)
  try {
    await _run('sc query com.docker.service', { shell: true });
    return 'service';
  } catch (err) {
    log.debug('Mirantis service probe failed:', err.message);
  }

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
 * @param {Function} deps.showRebootRequired  May return a Promise (must be awaited).
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
    isDesktopProcessRunning = () => isDockerDesktopProcessRunning(_run),
    waitForDesktopStart = (isRunning, timeoutMs, intervalMs, _sleep, progress) =>
      waitForDesktopProcessStart(isRunning, timeoutMs, intervalMs, _sleep, progress),
    diagnoseDocker = () => diagnoseWindowsDocker(_run),
    attemptRecover = (sp) => attemptRecoverWindowsDocker(_run, sp),
  } = deps;

  const state = await detectWindowsDockerState(isDaemonRunning, _findExe);

  if (state.action === 'none') return { result: 'already-running' };

  if (state.action === 'start' || state.action === 'start-service') {
    showProgress('Starting Docker Desktop… this can take up to 3 minutes on first launch.');
    if (state.action === 'start-service') {
      try {
        await _run('net start com.docker.service', { shell: true });
      } catch (err) {
        log.warn('Failed to start com.docker.service:', err.message);
      }
    } else if (state.exe) {
      try {
        spawnDetached(state.exe);
      } catch (err) {
        log.warn('Failed to spawn Docker Desktop executable:', err.message);
      }
    } else {
      try {
        await _run('start "" "Docker Desktop"', { shell: true });
      } catch (err) {
        log.warn('Failed to start Docker Desktop via shell fallback:', err.message);
      }
    }

    // Allow a grace window for delayed process spawn before declaring launch failure.
    let desktopRunning = await waitForDesktopStart(isDesktopProcessRunning, 25_000, 1_000, undefined, showProgress);
    if (!desktopRunning && state.action === 'start') {
      try {
        if (state.exe) {
          await _run(`start "" /min "${state.exe}"`, { shell: true });
        } else {
          await _run('start "" /min "Docker Desktop"', { shell: true });
        }
      } catch (err) {
        log.warn('Fallback Docker Desktop launch command failed:', err.message);
      }
      desktopRunning = await waitForDesktopStart(isDesktopProcessRunning, 15_000, 1_000, undefined, showProgress);
      if (!desktopRunning) {
        const launchErr = new Error(
          'Docker Desktop did not start. Please open Docker Desktop manually, wait until it is running, then retry.'
        );
        launchErr.code = 'DOCKER_DESKTOP_LAUNCH_FAILED';
        throw launchErr;
      }
    }

    let remainingMs = 180_000;
    let diagnostics = null;
    while (remainingMs > 0) {
      // Shorter slices re-run diagnosis sooner when the daemon is stuck (WSL / relaunch paths).
      const sliceMs = Math.min(12_000, remainingMs);
      const cameUpSlice = await _waitForDaemon(sliceMs, showProgress);
      if (cameUpSlice) return { result: 'started' };
      remainingMs -= sliceMs;
      diagnostics = await diagnoseDocker();

      // Proactively react to clear non-timeout conditions.
      if (diagnostics.issueCode === 'DOCKER_DESKTOP_NOT_RUNNING' && state.action === 'start') {
        showProgress('Docker Desktop not detected yet — relaunching quietly…');
        try {
          if (state.exe) await _run(`start "" /min "${state.exe}"`, { shell: true });
          else await _run('start "" /min "Docker Desktop"', { shell: true });
        } catch (err) {
          log.warn('Proactive Docker Desktop relaunch failed:', err.message);
        }
      }

      if (diagnostics.issueCode === 'WSL_NOT_INITIALIZED' || diagnostics.issueCode === 'WSL_BACKEND_MISSING') {
        if (await isDaemonRunning()) return { result: 'started' };
        break;
      }
    }

    diagnostics = diagnostics || await diagnoseDocker();
    if (diagnostics.issueCode === 'WSL_NOT_INITIALIZED' || diagnostics.issueCode === 'WSL_BACKEND_MISSING') {
      if (await isDaemonRunning()) return { result: 'started' };
      const recovery = await attemptRecover(showProgress);
      if (recovery.attempted && recovery.backendReady) {
        showProgress('WSL repaired — retrying Docker daemon startup…');
        const recovered = await _waitForDaemon(120_000, showProgress);
        if (recovered) return { result: 'started-after-recovery' };
      }
      if (await isDaemonRunning()) return { result: 'started-after-recovery' };
      const wslErr = new Error(
        'Docker backend (WSL) is not initialized. Run WSL setup, reboot if prompted, then open Docker Desktop and retry.'
      );
      wslErr.code = diagnostics.issueCode;
      wslErr.meta = { diagnostics, recovery };
      throw wslErr;
    }
    if (diagnostics.issueCode === 'DOCKER_DESKTOP_NOT_RUNNING') {
      const desktopErr = new Error('Docker Desktop is not running. Open Docker Desktop manually, wait until it is ready, then retry.');
      desktopErr.code = diagnostics.issueCode;
      desktopErr.meta = { diagnostics };
      throw desktopErr;
    }
    await Promise.resolve(showRebootRequired());
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
      'then reopen Fox in the box.';
    const installErr = new Error(msg);
    installErr.code = 'DOCKER_INSTALL_FAILED';
    throw installErr;
  });

  // Docker Desktop always requires a reboot after fresh install on Windows.
  // No point polling — show the reboot screen immediately.
  await Promise.resolve(showRebootRequired());
  return { result: 'reboot-required' };
}

module.exports = {
  runCommand,
  runCommandVerbose,
  waitForDaemon,
  waitForDesktopProcessStart,
  diagnoseWindowsDocker,
  attemptRecoverWindowsDocker,
  findDockerDesktopExe,
  detectWindowsDockerState,
  ensureDockerWindows,
};
