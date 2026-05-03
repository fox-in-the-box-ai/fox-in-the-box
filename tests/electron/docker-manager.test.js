'use strict';

jest.mock('dockerode');
jest.mock('electron-log', () => ({ info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() }));

const Dockerode = require('dockerode');
const docker    = require('../../packages/electron/src/docker-manager');
const { extractSetupStatusFromLogs } = require('../../packages/electron/src/docker-manager');
const fs = require('fs');

let mockDockerInstance;

beforeEach(() => {
  jest.clearAllMocks();
  mockDockerInstance = {
    ping:          jest.fn(),
    listImages:    jest.fn(),
    pull:          jest.fn(),
    listContainers: jest.fn(),
    createContainer: jest.fn(),
    getContainer:  jest.fn(),
    modem:         { followProgress: jest.fn() },
  };
  mockDockerInstance.listContainers.mockResolvedValue([]);
  Dockerode.mockImplementation(() => mockDockerInstance);
  docker.init();
});

afterEach(() => {
  jest.restoreAllMocks();
});

// ── Test cases ───────────────────────────────────────────────────────────────

test('isDaemonRunning returns true when ping succeeds', async () => {
  mockDockerInstance.ping.mockResolvedValue({});
  expect(await docker.isDaemonRunning()).toBe(true);
});

test('isDaemonRunning returns false when ping throws', async () => {
  mockDockerInstance.ping.mockRejectedValue(new Error('connect ENOENT'));
  expect(await docker.isDaemonRunning()).toBe(false);
});

test('isImagePresent returns true when image list is non-empty', async () => {
  mockDockerInstance.listImages.mockResolvedValue([{ Id: 'sha256:abc' }]);
  expect(await docker.isImagePresent()).toBe(true);
});

test('isImagePresent returns false when image list is empty', async () => {
  mockDockerInstance.listImages.mockResolvedValue([]);
  expect(await docker.isImagePresent()).toBe(false);
});

test('getRunningContainer returns null when no container matches', async () => {
  mockDockerInstance.listContainers.mockResolvedValue([]);
  expect(await docker.getRunningContainer()).toBeNull();
});

test('stopContainer is a no-op when container is not running', async () => {
  mockDockerInstance.listContainers.mockResolvedValue([]);
  // Should resolve without throwing
  await expect(docker.stopContainer()).resolves.toBeUndefined();
  // getContainer should NOT be called
  expect(mockDockerInstance.getContainer).not.toHaveBeenCalled();
});

test('startContainer uses FOX_DATA_DIR env var when set', async () => {
  process.env.FOX_DATA_DIR = '/custom/data/path';
  const mockContainer = { start: jest.fn().mockResolvedValue({}) };
  mockDockerInstance.createContainer.mockResolvedValue(mockContainer);

  await docker.startContainer();

  const call = mockDockerInstance.createContainer.mock.calls[0][0];
  expect(call.HostConfig.Binds[0]).toMatch(/^\/custom\/data\/path:/);
  delete process.env.FOX_DATA_DIR;
});

test('startContainer falls back to homedir path when FOX_DATA_DIR unset', async () => {
  delete process.env.FOX_DATA_DIR;
  const mockContainer = { start: jest.fn().mockResolvedValue({}) };
  mockDockerInstance.createContainer.mockResolvedValue(mockContainer);

  await docker.startContainer();

  const call = mockDockerInstance.createContainer.mock.calls[0][0];
  // Should contain some path ending in :/data — not empty
  expect(call.HostConfig.Binds[0]).toMatch(/.*:\/data$/);
});

test('startContainer reuses existing stopped container when present', async () => {
  mockDockerInstance.listContainers.mockResolvedValueOnce([
    { Id: 'abc', State: 'exited', Names: ['/fox-in-the-box'] },
  ]);
  const mockContainer = { start: jest.fn().mockResolvedValue({}) };
  mockDockerInstance.getContainer.mockReturnValue(mockContainer);

  await docker.startContainer();

  expect(mockDockerInstance.createContainer).not.toHaveBeenCalled();
  expect(mockContainer.start).toHaveBeenCalledTimes(1);
});

test('ensureContainerRunning reports already-running reason', async () => {
  mockDockerInstance.listContainers.mockResolvedValueOnce([
    { Id: 'run1', State: 'running', Names: ['/fox-in-the-box'] },
  ]);
  mockDockerInstance.getContainer.mockReturnValue({ start: jest.fn() });
  const result = await docker.ensureContainerRunning();
  expect(result.reason).toBe('already-running');
});

test('ensureContainerRunning reports started-existing reason', async () => {
  mockDockerInstance.listContainers.mockResolvedValueOnce([
    { Id: 'stop1', State: 'exited', Names: ['/fox-in-the-box'] },
  ]);
  const mockContainer = { start: jest.fn().mockResolvedValue({}) };
  mockDockerInstance.getContainer.mockReturnValue(mockContainer);
  const result = await docker.ensureContainerRunning();
  expect(result.reason).toBe('started-existing');
});

test('ensureContainerRunning reports created-new reason', async () => {
  mockDockerInstance.listContainers.mockResolvedValueOnce([]);
  const mockContainer = { start: jest.fn().mockResolvedValue({}) };
  mockDockerInstance.createContainer.mockResolvedValue(mockContainer);
  const result = await docker.ensureContainerRunning();
  expect(result.reason).toBe('created-new');
});

test('init on macOS falls back to user docker socket when default missing', () => {
  jest.spyOn(fs, 'existsSync').mockImplementation((target) => {
    if (target === '/var/run/docker.sock') return false;
    return String(target).includes('.docker') && String(target).includes('docker.sock');
  });

  docker.init({ platform: 'darwin' });

  expect(Dockerode).toHaveBeenLastCalledWith(
    expect.objectContaining({ socketPath: expect.stringContaining('.docker') })
  );
});

test('init on Windows configures docker_engine pipe first', () => {
  docker.init({ platform: 'win32' });
  expect(Dockerode).toHaveBeenLastCalledWith(
    expect.objectContaining({ socketPath: '//./pipe/docker_engine' })
  );
});

test('isDaemonRunning falls back to Docker Desktop Linux engine pipe on Windows', async () => {
  const firstClient = {
    ping: jest.fn().mockRejectedValue(new Error('connect ENOENT //./pipe/docker_engine')),
  };
  const secondClient = {
    ping: jest.fn().mockResolvedValue({}),
  };
  Dockerode
    .mockImplementationOnce(() => firstClient)
    .mockImplementationOnce(() => secondClient);

  docker.init({ platform: 'win32' });
  await expect(docker.isDaemonRunning()).resolves.toBe(true);
  expect(firstClient.ping).toHaveBeenCalled();
  expect(secondClient.ping).toHaveBeenCalled();
});

test('extractSetupStatusFromLogs parses cloning progress and install messages', () => {
  const lines = `
2026-05-03 15:12:16.621 | [entrypoint] Cloning hermes-agent @ v0.1.0 ...
2026-05-03 15:13:20.189 | Updating files:  50% (1355/2709)
2026-05-03 15:13:20.237 | [entrypoint] Installing hermes-agent ...
`;
  const parsed = extractSetupStatusFromLogs(lines, { currentApp: null });
  expect(parsed.currentApp).toBe('hermes-agent');
  expect(parsed.status).toBe('Installing hermes-agent dependencies…');
});

test('extractSetupStatusFromLogs treats Syncing like Cloning', () => {
  const lines = `
2026-05-03 15:12:16.621 | [entrypoint] Syncing hermes-webui @ v0.1.0 ...
`;
  const parsed = extractSetupStatusFromLogs(lines, { currentApp: null });
  expect(parsed.currentApp).toBe('hermes-webui');
  expect(parsed.status).toBe('Cloning hermes-webui repository…');
});

test('extractSetupStatusFromLogs shows image link phase', () => {
  const lines = `
2026-05-03 15:12:16.621 | [entrypoint] Hermes apps from container image (symlinks under /data/apps)
`;
  const parsed = extractSetupStatusFromLogs(lines, { currentApp: null });
  expect(parsed.status).toBe('Linking Hermes apps from image…');
});

test('extractSetupStatusFromLogs handles branch fallback message', () => {
  const lines = `
2026-05-03 15:12:16.621 | [entrypoint] Cloning hermes-webui @ v0.1.0 ...
2026-05-03 15:12:17.599 | [entrypoint] Tag v0.1.0 not found — falling back to default branch ...
`;
  const parsed = extractSetupStatusFromLogs(lines, { currentApp: null });
  expect(parsed.currentApp).toBe('hermes-webui');
  expect(parsed.status).toBe('hermes-webui tag not found, using default branch…');
});
