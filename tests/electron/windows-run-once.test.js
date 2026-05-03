'use strict';

jest.mock('electron-log', () => ({ info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() }));

const {
  registerWindowsRunOnceResume,
  RUN_ONCE_KEY,
  VALUE_NAME,
} = require('../../packages/electron/src/windows-run-once');

describe('registerWindowsRunOnceResume', () => {
  test('no-ops when platform is not win32', async () => {
    const run = jest.fn();
    await registerWindowsRunOnceResume('C:\\app\\fox.exe', { run, platform: 'linux' });
    expect(run).not.toHaveBeenCalled();
  });

  test('no-ops when exe path is empty', async () => {
    const run = jest.fn();
    await registerWindowsRunOnceResume('  ', { run, platform: 'win32' });
    expect(run).not.toHaveBeenCalled();
  });

  test('writes quoted exe path to HKCU RunOnce on Windows', async () => {
    const run = jest.fn().mockResolvedValue({ stdout: '', stderr: '' });
    await registerWindowsRunOnceResume('C:\\Program Files\\Fox\\app.exe', { run, platform: 'win32' });
    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0][0]).toBe('reg.exe');
    expect(run.mock.calls[0][1]).toEqual([
      'add',
      RUN_ONCE_KEY,
      '/v',
      VALUE_NAME,
      '/t',
      'REG_SZ',
      '/d',
      '"C:\\Program Files\\Fox\\app.exe"',
      '/f',
    ]);
    expect(run.mock.calls[0][2]).toMatchObject({ windowsHide: true });
  });

  test('swallows reg failures without throwing', async () => {
    const run = jest.fn().mockRejectedValue(new Error('Access denied'));
    await expect(
      registerWindowsRunOnceResume('C:\\app.exe', { run, platform: 'win32' }),
    ).resolves.toBeUndefined();
  });
});
