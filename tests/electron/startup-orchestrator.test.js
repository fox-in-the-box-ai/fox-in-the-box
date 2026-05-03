'use strict';

jest.mock('electron-log', () => ({ info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() }));

const { runStartup } = require('../../packages/electron/src/startup-orchestrator');

function makeDeps(overrides = {}) {
  const deps = {
    docker: {
      init: jest.fn(),
      isDaemonRunning: jest.fn().mockResolvedValue(true),
      isImagePresent: jest.fn().mockResolvedValue(true),
      pullImage: jest.fn().mockResolvedValue(undefined),
      ensureContainerRunning: jest.fn().mockResolvedValue({ reason: 'created-new' }),
      monitorContainerSetupLogs: jest.fn(() => jest.fn()),
    },
    waitUntilHealthy: jest.fn().mockResolvedValue(undefined),
    ensureDockerWindows: jest.fn().mockResolvedValue(undefined),
    installDockerMac: jest.fn().mockResolvedValue(undefined),
    waitForDaemon: jest.fn().mockResolvedValue(true),
    showProgress: jest.fn(),
    closeProgress: jest.fn(),
    openOnboarding: jest.fn().mockResolvedValue(undefined),
    onDaemonNotReady: jest.fn().mockResolvedValue(undefined),
    platform: 'win32',
    ...overrides,
  };
  return deps;
}

describe('runStartup', () => {
  test('runs through all phases and opens onboarding', async () => {
    const deps = makeDeps();
    const result = await runStartup(deps);

    expect(result.sessionId).toBeTruthy();
    expect(deps.docker.init).toHaveBeenCalledTimes(1);
    expect(deps.docker.ensureContainerRunning).toHaveBeenCalledTimes(1);
    expect(deps.waitUntilHealthy).toHaveBeenCalledTimes(1);
    expect(deps.docker.monitorContainerSetupLogs).toHaveBeenCalledTimes(1);
    expect(deps.openOnboarding).toHaveBeenCalledTimes(1);
    expect(deps.closeProgress).toHaveBeenCalledTimes(1);
  });

  test('waits for daemon on macOS after install', async () => {
    const deps = makeDeps({
      platform: 'darwin',
      docker: {
        init: jest.fn(),
        isDaemonRunning: jest
          .fn()
          .mockResolvedValueOnce(false)
          .mockResolvedValue(true),
        isImagePresent: jest.fn().mockResolvedValue(true),
        pullImage: jest.fn().mockResolvedValue(undefined),
        ensureContainerRunning: jest.fn().mockResolvedValue(undefined),
      },
    });

    await runStartup(deps);

    expect(deps.installDockerMac).toHaveBeenCalledTimes(1);
    expect(deps.waitForDaemon).toHaveBeenCalledWith(180000, expect.any(Function));
  });

  test('throws DAEMON_NOT_READY when setup completes but daemon stays down', async () => {
    const deps = makeDeps({
      platform: 'win32',
      docker: {
        init: jest.fn(),
        isDaemonRunning: jest.fn().mockResolvedValue(false),
        isImagePresent: jest.fn().mockResolvedValue(true),
        pullImage: jest.fn().mockResolvedValue(undefined),
        ensureContainerRunning: jest.fn().mockResolvedValue(undefined),
      },
    });

    await expect(runStartup(deps)).rejects.toMatchObject({
      phase: 'docker_daemon_ready',
      code: 'DAEMON_NOT_READY',
    });
    expect(deps.onDaemonNotReady).toHaveBeenCalledTimes(1);
  });

  test('Windows reboot-required skips second daemon prompt and ends startup cleanly', async () => {
    const deps = makeDeps({
      platform: 'win32',
      docker: {
        init: jest.fn(),
        isDaemonRunning: jest.fn().mockResolvedValue(false),
        isImagePresent: jest.fn().mockResolvedValue(true),
        pullImage: jest.fn().mockResolvedValue(undefined),
        ensureContainerRunning: jest.fn().mockResolvedValue(undefined),
      },
      ensureDockerWindows: jest.fn().mockResolvedValue({ result: 'reboot-required' }),
    });

    const out = await runStartup(deps);
    expect(out).toMatchObject({ outcome: 'reboot-required' });
    expect(deps.onDaemonNotReady).not.toHaveBeenCalled();
    expect(deps.closeProgress).toHaveBeenCalled();
  });

  test('shows explicit message when container already running', async () => {
    const deps = makeDeps({
      docker: {
        init: jest.fn(),
        isDaemonRunning: jest.fn().mockResolvedValue(true),
        isImagePresent: jest.fn().mockResolvedValue(true),
        pullImage: jest.fn().mockResolvedValue(undefined),
        ensureContainerRunning: jest.fn().mockResolvedValue({ reason: 'already-running' }),
        monitorContainerSetupLogs: jest.fn(() => jest.fn()),
      },
    });
    await runStartup(deps);
    expect(deps.showProgress).toHaveBeenCalledWith(expect.stringContaining('Container already running. Reusing existing instance…'));
  });
});
