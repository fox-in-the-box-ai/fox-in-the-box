'use strict';

/**
 * v0.7.18 #341 — Reset Fox tray menu.
 *
 * Failure mode this catches: prior to v0.7.18, the only way out of a broken
 * Fox install on Windows was a six-step manual dance — stop the container,
 * `docker rm`, `docker rmi ghcr.io/fox-in-the-box-ai/cloud:stable`,
 * `rd /s /q %APPDATA%\fox-in-the-box`, re-launch, re-onboard. We lived this
 * exact sequence debugging v0.7.16 → v0.7.17 on @roadhero's box. The Reset
 * Fox tray entry collapses that into one click, with a confirm dialog gating
 * the destructive action.
 *
 * tray-manager.js was at 0% Jest coverage when this spec landed. The
 * `resetFoxCompletely` handler is not directly exported, so this spec walks
 * the captured Menu template (via the mocked `electron.Menu.buildFromTemplate`)
 * to find the "Reset Fox completely…" item and invoke its `click` handler.
 *
 * What we pin here:
 *   1. The Cancel-confirm path (defaultId=0) early-returns without touching
 *      docker, the cleanup spawn, or app.quit() — accidental clicks must not
 *      delete user state.
 *   2. The Confirm-confirm path (response=1) calls docker.removeContainerAndImage,
 *      spawns the detached userData cleanup, and quits the app in that order
 *      — flipping the order leaves zombie containers or skips the cleanup.
 *   3. The dialog itself uses defaultId=cancelId=0 — Enter on the dialog must
 *      NOT wipe Fox.
 */

jest.mock('electron-log', () => ({
  info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn(),
}));

const mockTray = { setToolTip: jest.fn(), setContextMenu: jest.fn() };
let capturedMenuTemplate = null;

jest.mock('electron', () => ({
  app:   { quit: jest.fn(), getPath: jest.fn(() => '/fake/userData') },
  Tray:  jest.fn(() => mockTray),
  Menu:  {
    buildFromTemplate: jest.fn((template) => {
      capturedMenuTemplate = template;
      return { _template: template };
    }),
  },
  shell: { openExternal: jest.fn() },
  dialog: {
    showMessageBox: jest.fn(),
    showErrorBox:   jest.fn(),
  },
}));

jest.mock('child_process', () => ({ spawn: jest.fn(() => ({ unref: jest.fn() })) }));

jest.mock('../../packages/electron/src/docker-manager', () => ({
  removeContainerAndImage: jest.fn().mockResolvedValue(undefined),
  stopContainer:           jest.fn().mockResolvedValue(undefined),
  startContainer:          jest.fn().mockResolvedValue(undefined),
  restartContainer:        jest.fn().mockResolvedValue(undefined),
}));

jest.mock('../../packages/electron/src/updater', () => ({
  checkForUpdatesManual: jest.fn(),
}));

const { app, dialog } = require('electron');
const { spawn } = require('child_process');
const docker = require('../../packages/electron/src/docker-manager');
const tray = require('../../packages/electron/src/tray-manager');

function getResetClickHandler() {
  const item = capturedMenuTemplate.find((entry) =>
    typeof entry.label === 'string' && entry.label.startsWith('Reset Fox completely'),
  );
  if (!item) {
    throw new Error(
      'Could not find "Reset Fox completely…" item in tray menu template. ' +
      'If this test fails here, someone renamed or removed the tray menu ' +
      'entry — update both source and this test, and confirm #341 is still wired.',
    );
  }
  return item.click;
}

beforeEach(() => {
  jest.clearAllMocks();
  capturedMenuTemplate = null;
  tray.createTray(false);
});

test('Reset Fox tray entry is present in the built menu (#341 wiring)', () => {
  // Sanity: if a future refactor drops the menu entry entirely, every test
  // below also fails — but this assertion makes the cause obvious in CI.
  const labels = capturedMenuTemplate.map((e) => e.label).filter(Boolean);
  expect(labels).toEqual(
    expect.arrayContaining([expect.stringMatching(/^Reset Fox completely/)]),
  );
});

test('Reset Fox confirm dialog defaults to Cancel (defaultId=0, cancelId=0)', async () => {
  // Pre-check the dialog contract. Win11 dialogs treat Enter as defaultId
  // and Esc as cancelId. Both must point at Cancel so accidental keyboard
  // dismissal can never wipe Fox.
  dialog.showMessageBox.mockResolvedValueOnce({ response: 0 });
  await getResetClickHandler()();

  const call = dialog.showMessageBox.mock.calls[0][0];
  expect(call.defaultId).toBe(0);
  expect(call.cancelId).toBe(0);
  // Buttons in order: ['Cancel', 'Yes, reset everything'].
  expect(call.buttons[0]).toMatch(/cancel/i);
  expect(call.buttons[1]).toMatch(/reset/i);
});

test('Reset Fox: Cancel response is a no-op (no docker, no spawn, no quit)', async () => {
  // Cancel index = 0. The early `if (response !== 1) return;` guard must
  // fire BEFORE any side effects. Regression would be catastrophic: an
  // accidental click + Enter would wipe the user's container, image, and
  // userData with no further confirmation.
  dialog.showMessageBox.mockResolvedValueOnce({ response: 0 });

  await getResetClickHandler()();

  expect(docker.removeContainerAndImage).not.toHaveBeenCalled();
  expect(spawn).not.toHaveBeenCalled();
  expect(app.quit).not.toHaveBeenCalled();
});

test('Reset Fox: Confirm response runs docker cleanup, spawns detached cleanup, then quits — in order', async () => {
  // Confirm index = 1. The contract is sequence-sensitive:
  //   1. docker.removeContainerAndImage() — synchronous-ish, runs while
  //      Electron is alive so its docker socket is still open.
  //   2. spawnDetachedCleanup() — detached child that polls for Electron
  //      exit, then `rd /s /q`s userData. Must be spawned BEFORE quit so
  //      the process exists by the time Electron tears down.
  //   3. app.quit() — actually closes Electron, releases LevelDB locks,
  //      lets the spawned cleanup delete userData.
  // Out-of-order regression: if spawn fires after quit, userData survives
  // and the "reset" silently does nothing on the userData side.
  dialog.showMessageBox.mockResolvedValueOnce({ response: 1 });

  await getResetClickHandler()();

  expect(docker.removeContainerAndImage).toHaveBeenCalledTimes(1);
  expect(spawn).toHaveBeenCalledTimes(1);
  expect(app.quit).toHaveBeenCalledTimes(1);

  const dockerOrder = docker.removeContainerAndImage.mock.invocationCallOrder[0];
  const spawnOrder  = spawn.mock.invocationCallOrder[0];
  const quitOrder   = app.quit.mock.invocationCallOrder[0];
  expect(dockerOrder).toBeLessThan(spawnOrder);
  expect(spawnOrder).toBeLessThan(quitOrder);
});

test('Reset Fox: docker cleanup failure does NOT abort the userData wipe + quit', async () => {
  // If `docker rm` fails (daemon down, container already gone, etc.) the
  // user-state cleanup must still run — otherwise a broken Docker install
  // permanently blocks the Reset escape hatch, defeating the whole feature.
  dialog.showMessageBox.mockResolvedValueOnce({ response: 1 });
  docker.removeContainerAndImage.mockRejectedValueOnce(new Error('daemon down'));

  await getResetClickHandler()();

  expect(spawn).toHaveBeenCalledTimes(1);
  expect(app.quit).toHaveBeenCalledTimes(1);
});

test('Reset Fox: spawn args target the resolved userData path (#341 path correctness)', async () => {
  // The detached cleanup needs the EXACT userData path Electron resolved
  // (post-v0.7.19 this is the productName=fox-in-the-box path, with the
  // legacy @fox-in-the-box migration shim already run). Hard-coding the
  // wrong path would leave the old userData on disk forever.
  dialog.showMessageBox.mockResolvedValueOnce({ response: 1 });
  app.getPath.mockReturnValueOnce('/Users/test/Library/Application Support/fox-in-the-box');

  await getResetClickHandler()();

  // Either spawn arg list contains the userData path somewhere (cmd /c on
  // Windows, sh -c on mac/linux — both shell-quote it inline).
  const allSpawnArgs = JSON.stringify(spawn.mock.calls);
  expect(allSpawnArgs).toContain('/Users/test/Library/Application Support/fox-in-the-box');
});
