'use strict';

jest.mock('electron-log', () => ({ info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() }));

const { EventEmitter } = require('events');
const log = require('electron-log');
const { installStdioGuard } = require('../../packages/electron/src/stdio-guard');

describe('installStdioGuard', () => {
  let originalStdout;
  let originalStderr;

  beforeEach(() => {
    jest.clearAllMocks();
    originalStdout = Object.getOwnPropertyDescriptor(process, 'stdout');
    originalStderr = Object.getOwnPropertyDescriptor(process, 'stderr');
  });

  afterEach(() => {
    Object.defineProperty(process, 'stdout', originalStdout);
    Object.defineProperty(process, 'stderr', originalStderr);
  });

  // Swap BOTH streams so the guard never attaches listeners to the real
  // process streams during the test run.
  function swapStreams() {
    const out = new EventEmitter();
    const err = new EventEmitter();
    Object.defineProperty(process, 'stdout', { value: out, configurable: true });
    Object.defineProperty(process, 'stderr', { value: err, configurable: true });
    return { out, err };
  }

  test('an EPIPE error on stdout no longer throws after the guard is installed', () => {
    const { out } = swapStreams();
    const epipe = Object.assign(new Error('write EPIPE'), { code: 'EPIPE' });

    // Without a handler, EventEmitter turns 'error' into a throw — the
    // exact escalation path that produced the #748 crash dialog.
    expect(() => out.emit('error', epipe)).toThrow('write EPIPE');

    installStdioGuard();
    expect(() => out.emit('error', epipe)).not.toThrow();
    expect(log.warn).not.toHaveBeenCalled(); // EPIPE is expected noise — silent
  });

  test('guards stderr as well', () => {
    const { err } = swapStreams();
    installStdioGuard();
    expect(() => err.emit('error', Object.assign(new Error('write EPIPE'), { code: 'EPIPE' }))).not.toThrow();
  });

  test('a non-EPIPE stream error is swallowed but recorded once via the logger', () => {
    const { out } = swapStreams();
    installStdioGuard();
    const weird = Object.assign(new Error('boom'), { code: 'EIO' });
    expect(() => out.emit('error', weird)).not.toThrow();
    expect(() => out.emit('error', weird)).not.toThrow();
    expect(log.warn).toHaveBeenCalledTimes(1);
    expect(log.warn.mock.calls[0][0]).toContain('EIO');
  });

  test('tolerates absent or handler-less streams', () => {
    Object.defineProperty(process, 'stdout', { value: undefined, configurable: true });
    Object.defineProperty(process, 'stderr', { value: {}, configurable: true });
    expect(() => installStdioGuard()).not.toThrow();
  });
});
