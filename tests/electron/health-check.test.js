'use strict';

jest.mock('electron-log', () => ({ info: jest.fn(), warn: jest.fn(), debug: jest.fn(), error: jest.fn() }));
jest.mock('http', () => ({ get: jest.fn() }));

const http = require('http');
const { waitUntilHealthy } = require('../../packages/electron/src/health-check');

describe('waitUntilHealthy', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('serializes health checks without overlapping requests', async () => {
    let calls = 0;
    let inFlight = 0;
    let maxInFlight = 0;

    http.get.mockImplementation((_url, cb) => {
      calls += 1;
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      const req = {
        _onError: null,
        on(event, handler) {
          if (event === 'error') this._onError = handler;
        },
        setTimeout() {},
        destroy(err) {
          if (this._onError) this._onError(err || new Error('timeout'));
          inFlight -= 1;
        },
      };

      setTimeout(() => {
        if (calls < 3) {
          if (req._onError) req._onError(new Error('not ready'));
        } else {
          cb({ statusCode: 200, resume: () => {} });
        }
        inFlight -= 1;
      }, 10);

      return req;
    });

    await waitUntilHealthy({
      timeoutMs: 4000,
      intervalMs: 1,
      requestTimeoutMs: 200,
    });

    expect(maxInFlight).toBe(1);
    expect(calls).toBeGreaterThanOrEqual(3);
  });

  test('rejects with HEALTH_TIMEOUT when service never becomes healthy', async () => {
    http.get.mockImplementation(() => {
      const req = {
        _onError: null,
        on(event, handler) {
          if (event === 'error') this._onError = handler;
        },
        setTimeout() {},
        destroy(err) {
          if (this._onError) this._onError(err || new Error('timeout'));
        },
      };
      setTimeout(() => {
        if (req._onError) req._onError(new Error('connection refused'));
      }, 2);
      return req;
    });

    await expect(waitUntilHealthy({
      timeoutMs: 50,
      intervalMs: 1,
      requestTimeoutMs: 10,
    })).rejects.toMatchObject({ code: 'HEALTH_TIMEOUT' });
  });

  test('does not resolve after timeout even with late response callback', async () => {
    http.get.mockImplementation((_url, cb) => {
      const req = {
        _onError: null,
        on(event, handler) {
          if (event === 'error') this._onError = handler;
        },
        setTimeout(_ms, onTimeout) {
          setTimeout(onTimeout, 5);
        },
        destroy(err) {
          if (this._onError) this._onError(err || new Error('timeout'));
          // Late success callback should not flip result.
          setTimeout(() => cb({ statusCode: 200, resume: () => {} }), 20);
        },
      };
      return req;
    });

    await expect(waitUntilHealthy({
      timeoutMs: 30,
      intervalMs: 1,
      requestTimeoutMs: 5,
    })).rejects.toMatchObject({ code: 'HEALTH_TIMEOUT' });
  });
});
