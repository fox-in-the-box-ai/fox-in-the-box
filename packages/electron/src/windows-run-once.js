'use strict';

const { execFile } = require('child_process');
const { promisify } = require('util');
const log = require('electron-log');

const execFileAsync = promisify(execFile);

const RUN_ONCE_KEY = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\RunOnce';
const VALUE_NAME = 'FoxInTheBoxResumeSetup';

/**
 * Register this executable to launch once at the next Windows user logon (RunOnce).
 * Used after Docker setup requires a reboot so the user returns to the app automatically.
 *
 * @param {string} exePath  Absolute path to the running .exe (e.g. app.getPath('exe'))
 * @param {{ run?: typeof execFileAsync, platform?: string }} [opts]
 */
async function registerWindowsRunOnceResume(exePath, opts = {}) {
  const platform = opts.platform != null ? opts.platform : process.platform;
  if (platform !== 'win32') return;

  const run = opts.run || execFileAsync;
  const normalized = String(exePath || '').trim();
  if (!normalized) {
    log.warn('[run-once] Skipping RunOnce: empty exe path');
    return;
  }

  const inner = normalized.replace(/"/g, '');
  const regData = `"${inner}"`;

  try {
    await run(
      'reg.exe',
      ['add', RUN_ONCE_KEY, '/v', VALUE_NAME, '/t', 'REG_SZ', '/d', regData, '/f'],
      { windowsHide: true },
    );
    log.info('[run-once] Registered resume at next logon:', RUN_ONCE_KEY, VALUE_NAME);
  } catch (err) {
    log.warn('[run-once] Failed to register RunOnce resume:', err.message);
  }
}

module.exports = {
  registerWindowsRunOnceResume,
  RUN_ONCE_KEY,
  VALUE_NAME,
};
