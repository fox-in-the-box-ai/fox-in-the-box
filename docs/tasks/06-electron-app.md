# Task 06: Electron Desktop App

| Field          | Value                                                                    |
|----------------|--------------------------------------------------------------------------|
| **Status**     | Ready                                                                    |
| **Executor**   | AI agent                                                                 |
| **Depends on** | Task 01 (GitHub repo), Task 02 (monorepo scaffold), Task 03 (Dockerfile) |
| **Parallel**   | Task 05 (onboarding wizard) — can run concurrently                       |
| **Blocks**     | Task 07 (CI/CD release pipeline — needs packaged installer artifacts)    |
| **Path**       | `packages/electron/`                                                     |

---

## Summary

Build the Electron desktop app that manages the Fox in the Box Docker container.
The app is a **tray-only** application — no persistent window is shown after
initial setup dialogs. It checks for Docker, pulls the container image if
missing, starts the container, polls until healthy, then opens the browser and
parks in the system tray.

Primary target: **Windows** (NSIS installer, x64).  
Secondary target: **macOS** (unsigned `.zip` of `.app`).

No React, no bundler, no TypeScript — plain JavaScript in the Electron main
process only.

---

## Prerequisites

1. **Task 01 complete** — GitHub repository exists; `ghcr.io/fox-in-the-box-ai/cloud:stable`
   is the canonical image ref used throughout this task.
2. **Task 02 complete** — monorepo scaffold is in place (`pnpm` workspaces,
   `packages/` directory exists).
3. **Task 03 complete** — Docker image builds; the container exposes port `8787`
   and responds to `GET /health`.
4. The agent has Node.js 20+ and `pnpm` available in the build environment.

---

## Design Constraints

| Concern            | Decision                                                          |
|--------------------|-------------------------------------------------------------------|
| UI framework       | **None** — Electron main process only, no renderer window        |
| Bundler            | **None** — `src/` files loaded directly by Electron              |
| Docker API         | `dockerode` npm package (not raw `docker` CLI calls)             |
| Logging            | `electron-log` (writes to platform log dir)                      |
| Packaging          | `electron-builder` via `pnpm build`                              |
| Windows target     | NSIS `.exe` installer, x64                                        |
| macOS target       | Unsigned `.zip` of `.app` (no Apple Developer account required)  |
| App ID             | `io.foxinthebox.desktop`                                         |
| Product name       | `Fox in the Box`                                                  |
| Container image    | `ghcr.io/fox-in-the-box-ai/cloud:stable`                         |
| Container name     | `fox-in-the-box`                                                  |
| Data volume        | `~/.foxinthebox:/data`                                           |
| Port binding       | `127.0.0.1:8787:8787`                                            |

---

## Implementation

### Step 1 — Scaffold `packages/electron/`

Create the directory tree and bare `package.json`:

```
packages/electron/
├── assets/
│   └── icon.png            ← 1024×1024 PNG placeholder (copy any square PNG)
├── src/
│   ├── main.js
│   ├── docker-manager.js
│   ├── tray-manager.js
│   └── health-check.js
├── electron-builder.yml
└── package.json
```

Verify the workspace root's `pnpm-workspace.yaml` already references
`packages/*`; if not, add it.

---

### Step 2 — `packages/electron/package.json`

```json
{
  "name": "@fox-in-the-box/electron",
  "version": "0.1.0",
  "description": "Fox in the Box desktop app",
  "main": "src/main.js",
  "scripts": {
    "start": "electron .",
    "build": "electron-builder",
    "build:win": "electron-builder --win",
    "build:mac": "electron-builder --mac",
    "test": "jest --testPathPattern=tests/electron"
  },
  "dependencies": {
    "dockerode": "^4.0.2",
    "electron-log": "^5.1.2"
  },
  "devDependencies": {
    "electron": "^28.0.0",
    "electron-builder": "^24.9.1",
    "jest": "^29.7.0"
  },
  "build": {
    "extends": "./electron-builder.yml"
  }
}
```

> **Note:** `electron` is a devDependency because `electron-builder` bundles its
> own copy at package time.

---

### Step 3 — `packages/electron/electron-builder.yml`

```yaml
appId: io.foxinthebox.desktop
productName: Fox in the Box
copyright: "Copyright © 2024 Fox in the Box AI"

directories:
  output: dist

files:
  - src/**/*
  - assets/**/*
  - package.json

icon: assets/icon.png

win:
  target:
    - target: nsis
      arch:
        - x64
  artifactName: "fox-in-the-box-setup-${version}-${arch}.exe"

nsis:
  oneClick: true
  perMachine: false
  allowToChangeInstallationDirectory: false
  deleteAppDataOnUninstall: false

mac:
  target:
    - target: zip
      arch:
        - x64
        - arm64
  artifactName: "fox-in-the-box-${version}-${arch}-mac.zip"
  identity: null   # unsigned build

publish: null      # no auto-update endpoint yet
```

---

### Step 4 — `packages/electron/src/docker-manager.js`

This module owns **all Docker operations**. It uses `dockerode` exclusively —
no `child_process` shell-outs to `docker` CLI for container management.

```js
'use strict';

const Dockerode = require('dockerode');
const log = require('electron-log');

const IMAGE  = 'ghcr.io/fox-in-the-box-ai/cloud:stable';
const CNAME  = 'fox-in-the-box';
const PORT   = '8787/tcp';

let docker = null;

/** Initialise the Dockerode client (called once from main.js). */
function init() {
  docker = new Dockerode();
}

/**
 * Returns true if the Docker daemon is reachable.
 * Throws if Dockerode cannot be initialised.
 */
async function isDaemonRunning() {
  try {
    await docker.ping();
    return true;
  } catch (err) {
    log.warn('Docker daemon not reachable:', err.message);
    return false;
  }
}

/**
 * Returns true if the image is already present locally.
 */
async function isImagePresent() {
  const images = await docker.listImages({ filters: { reference: [IMAGE] } });
  return images.length > 0;
}

/**
 * Pull the image with a progress callback.
 * @param {(pct: number) => void} onProgress  0–100
 */
async function pullImage(onProgress) {
  return new Promise((resolve, reject) => {
    docker.pull(IMAGE, (err, stream) => {
      if (err) return reject(err);
      docker.modem.followProgress(stream, onFinish, onEvent);

      function onEvent(evt) {
        if (evt.progressDetail && evt.progressDetail.total) {
          const pct = Math.round(
            (evt.progressDetail.current / evt.progressDetail.total) * 100
          );
          onProgress(pct);
        }
      }
      function onFinish(err2) {
        if (err2) reject(err2);
        else resolve();
      }
    });
  });
}

/**
 * Returns the running container object or null.
 */
async function getRunningContainer() {
  const containers = await docker.listContainers({
    filters: { name: [CNAME] },
  });
  if (containers.length === 0) return null;
  return containers[0];
}

/**
 * Start the Fox container. Assumes image is already present.
 * Returns the container object.
 */
async function startContainer() {
  const os = require('os');
  const path = require('path');
  const dataDir = path.join(os.homedir(), '.foxinthebox');

  const container = await docker.createContainer({
    name: CNAME,
    Image: IMAGE,
    HostConfig: {
      AutoRemove: true,
      CapAdd: ['NET_ADMIN'],
      Sysctls: { 'net.ipv4.ip_forward': '1' },
      PortBindings: {
        [PORT]: [{ HostIp: '127.0.0.1', HostPort: '8787' }],
      },
      Binds: [`${dataDir}:/data`],
    },
    ExposedPorts: { [PORT]: {} },
  });

  await container.start();
  log.info('Container started:', CNAME);
  return container;
}

/**
 * Stop the named container with a 10-second timeout.
 */
async function stopContainer() {
  const containers = await docker.listContainers({
    filters: { name: [CNAME] },
  });
  if (containers.length === 0) {
    log.info('stopContainer: container not running, nothing to stop');
    return;
  }
  const container = docker.getContainer(containers[0].Id);
  await container.stop({ t: 10 });
  log.info('Container stopped:', CNAME);
}

/**
 * Restart the named container.
 */
async function restartContainer() {
  const containers = await docker.listContainers({
    filters: { name: [CNAME] },
  });
  if (containers.length === 0) throw new Error('Container not running');
  const container = docker.getContainer(containers[0].Id);
  await container.restart({ t: 10 });
  log.info('Container restarted:', CNAME);
}

module.exports = {
  init,
  isDaemonRunning,
  isImagePresent,
  pullImage,
  getRunningContainer,
  startContainer,
  stopContainer,
  restartContainer,
};
```

---

### Step 5 — `packages/electron/src/health-check.js`

```js
'use strict';

const http = require('http');
const log  = require('electron-log');

const HEALTH_URL    = 'http://localhost:8787/health';
const MAX_ATTEMPTS  = 30;
const INTERVAL_MS   = 1000;

/**
 * Poll /health until HTTP 200 is received or max attempts are exhausted.
 * @returns {Promise<void>}  Resolves when healthy, rejects on timeout.
 */
function waitUntilHealthy() {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const timer = setInterval(() => {
      attempts += 1;
      log.info(`Health check attempt ${attempts}/${MAX_ATTEMPTS}`);

      const req = http.get(HEALTH_URL, (res) => {
        if (res.statusCode === 200) {
          clearInterval(timer);
          log.info('Container healthy');
          resolve();
        }
        res.resume(); // drain
      });

      req.on('error', (err) => {
        log.debug('Health check error (expected during startup):', err.message);
      });

      req.setTimeout(800, () => req.destroy());

      if (attempts >= MAX_ATTEMPTS) {
        clearInterval(timer);
        reject(new Error(`Container did not become healthy after ${MAX_ATTEMPTS}s`));
      }
    }, INTERVAL_MS);
  });
}

module.exports = { waitUntilHealthy };
```

---

### Step 6 — `packages/electron/src/tray-manager.js`

```js
'use strict';

const { app, Tray, Menu, shell, dialog } = require('electron');
const path   = require('path');
const log    = require('electron-log');
const docker = require('./docker-manager');

const ICON_PATH = path.join(__dirname, '..', 'assets', 'icon.png');
const APP_URL   = 'http://localhost:8787';

let tray       = null;
let isRunning  = false;

function setRunning(state) {
  isRunning = state;
  if (tray) buildMenu();
}

function buildMenu() {
  const statusLabel = isRunning ? '🟢 Fox is running' : '🔴 Fox is stopped';

  const menu = Menu.buildFromTemplate([
    { label: statusLabel, enabled: false },
    { type: 'separator' },
    {
      label: 'Open Fox',
      click: () => shell.openExternal(APP_URL),
    },
    {
      label: 'Restart Fox',
      click: async () => {
        try {
          await docker.restartContainer();
        } catch (err) {
          log.error('Restart failed:', err.message);
          dialog.showErrorBox('Restart failed', err.message);
        }
      },
    },
    {
      label: isRunning ? 'Stop Fox' : 'Start Fox',
      click: async () => {
        try {
          if (isRunning) {
            await docker.stopContainer();
            setRunning(false);
          } else {
            await docker.startContainer();
            setRunning(true);
          }
        } catch (err) {
          log.error('Toggle failed:', err.message);
          dialog.showErrorBox('Error', err.message);
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: async () => {
        log.info('Quit requested — stopping container');
        try {
          await docker.stopContainer();
        } catch (err) {
          log.warn('Stop on quit failed (container may already be stopped):', err.message);
        }
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(menu);
}

/**
 * Create the system tray icon and initial menu.
 * @param {boolean} running  Initial running state.
 */
function createTray(running) {
  tray      = new Tray(ICON_PATH);
  isRunning = running;

  tray.setToolTip('Fox in the Box');
  buildMenu();

  log.info('Tray created');
}

module.exports = { createTray, setRunning };
```

---

### Step 7 — `packages/electron/src/main.js`

The entry point orchestrates the startup sequence. It intentionally creates
**no `BrowserWindow`** — dialogs are shown via `dialog.showMessageBox` /
`dialog.showErrorBox` and the app parks in the tray.

```js
'use strict';

const { app, dialog } = require('electron');
const { exec }        = require('child_process');
const log             = require('electron-log');
const docker          = require('./docker-manager');
const { waitUntilHealthy } = require('./health-check');
const { createTray, setRunning } = require('./tray-manager');
const { shell }       = require('electron');

// Prevent multiple instances
if (!app.requestSingleInstanceLock()) {
  app.quit();
  process.exit(0);
}

// Keep app alive when all windows are closed (tray-only)
app.on('window-all-closed', (e) => e.preventDefault());

app.whenReady().then(main).catch((err) => {
  log.error('Fatal startup error:', err);
  dialog.showErrorBox('Fox in the Box — startup error', err.message);
  app.quit();
});

// ─── Helpers ────────────────────────────────────────────────────────────────

function runCommand(cmd) {
  return new Promise((resolve, reject) => {
    exec(cmd, (error, stdout, stderr) => {
      if (error) reject(new Error(stderr || error.message));
      else resolve(stdout);
    });
  });
}

async function installDocker() {
  const platform = process.platform;
  const instruction =
    platform === 'win32'
      ? 'winget install Docker.DockerDesktop'
      : 'brew install --cask docker';

  const { response } = await dialog.showMessageBox({
    type: 'question',
    buttons: ['Install Docker', 'Cancel'],
    defaultId: 0,
    cancelId: 1,
    title: 'Docker not found',
    message: 'Docker Desktop is required but was not found.',
    detail: `Fox in the Box will run:\n\n  ${instruction}\n\nThis may take several minutes.`,
  });

  if (response !== 0) throw new Error('User cancelled Docker installation');

  log.info('Installing Docker:', instruction);
  await runCommand(instruction);
  log.info('Docker install command finished — waiting 5s for daemon');
  await new Promise((r) => setTimeout(r, 5000));
}

// ─── Main startup sequence ───────────────────────────────────────────────────

async function main() {
  log.info('Fox in the Box starting up');

  // 1. Initialise Docker client
  docker.init();

  // 2. Check Docker daemon
  let dockerRunning = await docker.isDaemonRunning();
  if (!dockerRunning) {
    await installDocker();
    dockerRunning = await docker.isDaemonRunning();
    if (!dockerRunning) {
      throw new Error(
        'Docker daemon still not reachable after install. ' +
        'Please start Docker Desktop manually and relaunch Fox in the Box.'
      );
    }
  }

  // 3. Pull image if not present
  if (!(await docker.isImagePresent())) {
    log.info('Image not found locally — pulling');
    await new Promise((resolve, reject) => {
      // Show a non-blocking info notice; dismiss automatically when done
      const notice = dialog.showMessageBox({
        type: 'info',
        buttons: [],
        title: 'Fox in the Box',
        message: 'Downloading Fox in the Box…',
        detail: 'This only happens once. Please wait.',
      });
      docker.pullImage((pct) => log.info(`Pull progress: ${pct}%`))
        .then(() => { resolve(); })
        .catch(reject);
    });
    log.info('Image pull complete');
  }

  // 4. Start container if not already running
  const running = await docker.getRunningContainer();
  if (!running) {
    log.info('Container not running — starting');
    await docker.startContainer();
  } else {
    log.info('Container already running');
  }

  // 5. Wait for health
  log.info('Waiting for container to become healthy');
  await waitUntilHealthy();

  // 6. Open browser
  log.info('Opening browser at http://localhost:8787');
  await shell.openExternal('http://localhost:8787');

  // 7. Create tray icon
  createTray(true);
  setRunning(true);
}
```

---

### Step 8 — `assets/icon.png` placeholder

Copy **any** square PNG (at least 256×256) to `packages/electron/assets/icon.png`.
A suitable placeholder can be generated with ImageMagick if present:

```bash
convert -size 1024x1024 xc:'#FF6B35' \
  -font DejaVu-Sans -pointsize 500 -fill white \
  -gravity center -annotate 0 '🦊' \
  packages/electron/assets/icon.png
```

Or simply copy an existing project icon. The file **must exist** for
`electron-builder` to succeed — a blank PNG is acceptable for this task.

---

### Step 9 — Unit tests `tests/electron/docker-manager.test.js`

Place tests at the workspace root under `tests/electron/` (parallel to
`packages/electron/`).

```js
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
```

---

## File Checklist

After completing this task the following files must exist:

```
packages/electron/
├── assets/
│   └── icon.png                        ← placeholder 1024×1024 PNG
├── src/
│   ├── main.js                         ← app entry point
│   ├── docker-manager.js               ← all Docker operations
│   ├── tray-manager.js                 ← tray icon + menu
│   └── health-check.js                 ← /health polling loop
├── electron-builder.yml                ← packaging config
└── package.json                        ← scripts + deps + builder ref

tests/electron/
└── docker-manager.test.js              ← jest unit tests (6 test cases)
```

---

## Acceptance Criteria

All criteria must pass before this task is considered complete.

| #  | Criterion | How to verify |
|----|-----------|---------------|
| 1  | `pnpm build` in `packages/electron/` exits 0 and produces installer artifacts | Run on `windows-latest` and `macos-latest` GitHub Actions runners; check `dist/` for `.exe` and `.zip` |
| 2  | On launch with Docker running and container not started: container is running within 15 seconds | Start app with container absent; run `docker ps --filter name=fox-in-the-box` within 15 s |
| 3  | Browser opens to `http://localhost:8787` after container passes health check | Observe default browser launch during manual test |
| 4  | Tray appears with items in correct order: status label → Open Fox → Restart Fox → Stop Fox → *(separator)* → Quit | Right-click tray icon and verify menu order visually |
| 5  | "Stop Fox" from tray: container stops, status label updates to "Fox is stopped" | Click Stop Fox; run `docker ps` to confirm no running container; re-open tray menu |
| 6  | Quit from tray: container stops within 10 seconds, Electron process exits cleanly (exit code 0) | Click Quit; run `docker ps` within 10 s; verify no lingering `electron` process |
| 7  | No Electron window appears during normal operation (tray only) | Inspect taskbar / window list — only tray icon is visible after startup dialogs |

---

## Test Cases (Jest — `docker-manager.test.js`)

Six required test cases, each using a `dockerode` mock:

| # | Test name | Description |
|---|-----------|-------------|
| 1 | `isDaemonRunning returns true when ping succeeds` | Mock `docker.ping()` resolves → function returns `true` |
| 2 | `isDaemonRunning returns false when ping throws` | Mock `docker.ping()` rejects → function returns `false` (does not throw) |
| 3 | `isImagePresent returns true when image list is non-empty` | Mock `listImages` returns `[{ Id: '...' }]` → returns `true` |
| 4 | `isImagePresent returns false when image list is empty` | Mock `listImages` returns `[]` → returns `false` |
| 5 | `getRunningContainer returns null when no container matches` | Mock `listContainers` returns `[]` → returns `null` |
| 6 | `stopContainer is a no-op when container is not running` | Mock `listContainers` returns `[]` → resolves without calling `getContainer` |

Run with:

```bash
# From workspace root
pnpm --filter @fox-in-the-box/electron test
# or
cd packages/electron && npx jest --testPathPattern=tests/electron
```

---

## Manual Acceptance Checklist

Performed by a human tester on a real machine (Windows primary, macOS secondary):

- [ ] 1. Fresh install: Docker Desktop not installed → app prompts to install → Docker installs → app continues startup sequence.
- [ ] 2. Docker installed but not running → app surfaces clear error dialog and exits gracefully.
- [ ] 3. First launch (image absent): pull progress logged to `electron-log` log file; container starts after pull completes.
- [ ] 4. Subsequent launch (image present): container starts without pull step, startup is faster.
- [ ] 5. Tray icon visible in system tray with correct tooltip ("Fox in the Box").
- [ ] 6. "Open Fox" menu item opens `http://localhost:8787` in default browser.
- [ ] 7. "Restart Fox" restarts container; browser reload shows app is back up within ~15 s.
- [ ] 8. "Stop Fox" stops container; status label updates; "Start Fox" re-appears in menu.
- [ ] 9. "Start Fox" (after stop) starts container and updates status label to "Fox is running".
- [ ] 10. "Quit" stops container within 10 s (verify with `docker ps`) and process exits — no orphan container left running.

---

## Notes

### Platform Priority

Windows is the **primary target**. All code paths involving Docker installation
(`winget`), path separators, and tray behaviour must be verified on Windows
first. macOS support is **best-effort** and ships unsigned — users must allow
the app via System Settings → Privacy & Security.

### GitHub Actions

Two runners are required in the release workflow (Task 07):

```yaml
strategy:
  matrix:
    os: [windows-latest, macos-latest]
```

The Windows runner produces the NSIS `.exe`; the macOS runner produces the
unsigned `.zip`. Neither runner requires Docker to be installed — the build
step only invokes `electron-builder` to package the app, not to run it.

### Docker Socket Access (macOS)

> **v0.1 scope note:** macOS is not a promoted install target for v0.1 — users
> on macOS should use the shell install script (`install.sh`) instead. The
> Electron app is built for macOS but ships unsigned and is not linked from the
> website. macOS-specific Electron behaviour is best-effort.

On macOS, `dockerode` connects to `/var/run/docker.sock` by default. However,
Docker Desktop on macOS may also expose the socket at
`~/.docker/run/docker.sock` (newer versions). If Docker Desktop is installed
but not yet started the socket will not exist; `isDaemonRunning()` handles this
by returning `false` and triggering the install/prompt flow.

For v0.1, the agent should try `/var/run/docker.sock` first, then fall back to
`~/.docker/run/docker.sock`, and surface a clear error if neither exists.

### `--rm` and `AutoRemove`

The container is started with `AutoRemove: true` (equivalent to `docker run --rm`).
This means the container disappears automatically once stopped — no explicit
`docker rm` call is needed in `stopContainer()` or `restartContainer()`.

### Logging

`electron-log` writes to the platform default log directory:
- **Windows:** `%APPDATA%\Fox in the Box\logs\main.log`
- **macOS:** `~/Library/Logs/Fox in the Box/main.log`

Include the log path in any user-facing error dialog to help with support.
