'use strict';

jest.mock('electron-log', () => ({
  info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn(),
}));

const {
  waitForDaemon,
  findDockerDesktopExe,
  detectWindowsDockerState,
  ensureDockerWindows,
} = require('../../packages/electron/src/startup');

// ─── waitForDaemon ────────────────────────────────────────────────────────────

describe('waitForDaemon', () => {
  test('returns true immediately when daemon is already up', async () => {
    const isDaemonRunning = jest.fn().mockResolvedValue(true);
    const result = await waitForDaemon(isDaemonRunning, 5000, 100);
    expect(result).toBe(true);
    expect(isDaemonRunning).toHaveBeenCalledTimes(1);
  });

  test('returns true after a few failed polls', async () => {
    const isDaemonRunning = jest.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(false)
      .mockResolvedValue(true);
    const sleep = jest.fn().mockResolvedValue(undefined);
    const result = await waitForDaemon(isDaemonRunning, 10_000, 100, Date.now, sleep);
    expect(result).toBe(true);
    expect(isDaemonRunning).toHaveBeenCalledTimes(3);
  });

  test('returns false when deadline expires without daemon coming up', async () => {
    const isDaemonRunning = jest.fn().mockResolvedValue(false);
    // Fake clock: first call returns t=0, subsequent calls jump past deadline
    let tick = 0;
    const now = () => (tick++ === 0 ? 0 : 99999);
    const sleep = jest.fn().mockResolvedValue(undefined);
    const result = await waitForDaemon(isDaemonRunning, 1000, 100, now, sleep);
    expect(result).toBe(false);
  });
});

// ─── findDockerDesktopExe ─────────────────────────────────────────────────────

describe('findDockerDesktopExe', () => {
  test('returns exe path when first candidate exists', async () => {
    const run = jest.fn().mockResolvedValueOnce(''); // first candidate found
    const result = await findDockerDesktopExe(run);
    expect(result).toContain('Docker Desktop.exe');
    expect(run).toHaveBeenCalledTimes(1);
  });

  test('tries second candidate when first is missing', async () => {
    const run = jest.fn()
      .mockRejectedValueOnce(new Error('not found')) // first candidate missing
      .mockResolvedValueOnce('');                     // second candidate found
    const result = await findDockerDesktopExe(run);
    expect(result).toContain('Docker Desktop.exe');
    expect(run).toHaveBeenCalledTimes(2);
  });

  test('returns "service" when no exe found but Mirantis service exists', async () => {
    const run = jest.fn()
      .mockRejectedValueOnce(new Error('not found'))  // first exe
      .mockRejectedValueOnce(new Error('not found'))  // second exe
      .mockResolvedValueOnce('SERVICE_NAME: com.docker.service'); // sc query
    const result = await findDockerDesktopExe(run);
    expect(result).toBe('service');
  });

  test('returns null when nothing is installed', async () => {
    const run = jest.fn().mockRejectedValue(new Error('not found'));
    const result = await findDockerDesktopExe(run);
    expect(result).toBeNull();
  });
});

// ─── detectWindowsDockerState ─────────────────────────────────────────────────

describe('detectWindowsDockerState', () => {
  test('returns "none" when daemon is already running', async () => {
    const isDaemonRunning = jest.fn().mockResolvedValue(true);
    const result = await detectWindowsDockerState(isDaemonRunning);
    expect(result).toEqual({ action: 'none' });
  });

  test('returns "install" when daemon is down and nothing is found', async () => {
    const isDaemonRunning = jest.fn().mockResolvedValue(false);
    const findExe = jest.fn().mockResolvedValue(null);
    const result = await detectWindowsDockerState(isDaemonRunning, findExe);
    expect(result).toEqual({ action: 'install' });
  });

  test('returns "start" with exe when Docker Desktop is installed', async () => {
    const isDaemonRunning = jest.fn().mockResolvedValue(false);
    const findExe = jest.fn().mockResolvedValue('C:\\Program Files\\Docker\\Docker Desktop.exe');
    const result = await detectWindowsDockerState(isDaemonRunning, findExe);
    expect(result).toEqual({ action: 'start', exe: 'C:\\Program Files\\Docker\\Docker Desktop.exe' });
  });

  test('returns "start-service" when Mirantis Engine is found', async () => {
    const isDaemonRunning = jest.fn().mockResolvedValue(false);
    const findExe = jest.fn().mockResolvedValue('service');
    const result = await detectWindowsDockerState(isDaemonRunning, findExe);
    expect(result).toEqual({ action: 'start-service' });
  });
});

// ─── ensureDockerWindows ──────────────────────────────────────────────────────

function makeDeps(overrides = {}) {
  return {
    isDaemonRunning:   jest.fn().mockResolvedValue(false),
    waitForDaemon:     jest.fn().mockResolvedValue(true),
    runCommand:        jest.fn().mockResolvedValue(''),
    spawnDetached:     jest.fn(),
    showProgress:      jest.fn(),
    showRebootRequired: jest.fn(),
    _findExe:          jest.fn().mockResolvedValue(null),
    ...overrides,
  };
}

describe('ensureDockerWindows', () => {
  test('returns "already-running" when daemon is up from the start', async () => {
    const deps = makeDeps({
      isDaemonRunning: jest.fn().mockResolvedValue(true),
    });
    const result = await ensureDockerWindows(deps);
    expect(result).toEqual({ result: 'already-running' });
    expect(deps.runCommand).not.toHaveBeenCalled();
    expect(deps.spawnDetached).not.toHaveBeenCalled();
  });

  test('spawns Desktop exe and returns "started" when daemon comes up', async () => {
    const deps = makeDeps({
      _findExe: jest.fn().mockResolvedValue('C:\\Docker\\Docker Desktop.exe'),
    });
    const result = await ensureDockerWindows(deps);
    expect(deps.spawnDetached).toHaveBeenCalledWith('C:\\Docker\\Docker Desktop.exe');
    expect(result).toEqual({ result: 'started' });
    expect(deps.showRebootRequired).not.toHaveBeenCalled();
  });

  test('shows reboot screen when Desktop found but daemon never comes up', async () => {
    const deps = makeDeps({
      _findExe:     jest.fn().mockResolvedValue('C:\\Docker\\Docker Desktop.exe'),
      waitForDaemon: jest.fn().mockResolvedValue(false),
    });
    const result = await ensureDockerWindows(deps);
    expect(deps.showRebootRequired).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ result: 'reboot-required' });
  });

  test('runs winget install when nothing is found', async () => {
    const deps = makeDeps();
    const result = await ensureDockerWindows(deps);
    expect(deps.runCommand).toHaveBeenCalledWith(
      expect.stringContaining('Docker.DockerDesktop'),
      expect.objectContaining({ shell: true })
    );
    expect(result).toEqual({ result: 'installed' });
  });

  test('shows reboot screen after install when daemon never starts', async () => {
    const deps = makeDeps({ waitForDaemon: jest.fn().mockResolvedValue(false) });
    const result = await ensureDockerWindows(deps);
    expect(deps.showRebootRequired).toHaveBeenCalledTimes(1);
    expect(result).toEqual({ result: 'reboot-required' });
  });

  test('throws user-friendly error when winget fails', async () => {
    const deps = makeDeps({
      runCommand: jest.fn().mockRejectedValue(new Error('winget not found')),
    });
    await expect(ensureDockerWindows(deps)).rejects.toThrow(
      'Could not install Docker Desktop automatically'
    );
  });

  test('starts Mirantis service via net start when service found', async () => {
    const deps = makeDeps({
      _findExe: jest.fn().mockResolvedValue('service'),
    });
    const result = await ensureDockerWindows(deps);
    expect(deps.runCommand).toHaveBeenCalledWith(
      'net start com.docker.service',
      expect.objectContaining({ shell: true })
    );
    expect(result).toEqual({ result: 'started' });
  });
});
