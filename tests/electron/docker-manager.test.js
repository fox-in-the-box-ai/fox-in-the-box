'use strict';

jest.mock('dockerode');
jest.mock('electron-log', () => ({ info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() }));

const Dockerode = require('dockerode');
const docker    = require('../../packages/electron/src/docker-manager');

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
  Dockerode.mockImplementation(() => mockDockerInstance);
  docker.init();
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
