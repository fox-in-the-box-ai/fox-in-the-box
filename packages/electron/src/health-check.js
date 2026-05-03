'use strict';

const http = require('http');
const log  = require('electron-log');

// Use IPv4 loopback explicitly because container port mapping is bound to 127.0.0.1.
// On some Windows setups, localhost resolves to ::1 first, causing false ECONNREFUSED.
const HEALTH_URL    = 'http://127.0.0.1:8787/health';
const INTERVAL_MS   = 1000;
const REQUEST_TIMEOUT_MS = 1500;
const HEALTH_TIMEOUT_MS = 120_000;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function requestHealth(url, timeoutMs) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      const statusCode = res.statusCode;
      res.resume(); // drain
      resolve({ ok: statusCode === 200, statusCode, error: null });
    });

    req.on('error', (err) => {
      resolve({ ok: false, statusCode: null, error: err.message });
    });

    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`health request timed out after ${timeoutMs}ms`));
    });
  });
}

/**
 * Poll /health until HTTP 200 is received or max attempts are exhausted.
 * @returns {Promise<void>}  Resolves when healthy, rejects on timeout.
 */
async function waitUntilHealthy({
  healthUrl = HEALTH_URL,
  timeoutMs = HEALTH_TIMEOUT_MS,
  intervalMs = INTERVAL_MS,
  requestTimeoutMs = REQUEST_TIMEOUT_MS,
  showProgress = null,
  failFastCheck = null,
} = {}) {
  const startedAt = Date.now();
  let attempts = 0;
  let lastStatus = null;
  let lastError = null;

  while ((Date.now() - startedAt) < timeoutMs) {
    attempts += 1;
    const elapsedMs = Date.now() - startedAt;
    if (showProgress) showProgress(`Waiting for app to start… ${Math.round(elapsedMs / 1000)}s`);
    log.info(`Health check attempt ${attempts} (${Math.round(elapsedMs / 1000)}s elapsed)`);

    if (typeof failFastCheck === 'function') {
      const failFastError = await failFastCheck({ attempts, elapsedMs, lastStatus, lastError });
      if (failFastError) {
        if (failFastError instanceof Error) throw failFastError;
        const err = new Error(failFastError.message || 'Startup aborted by proactive health checks');
        if (failFastError.code) err.code = failFastError.code;
        if (failFastError.meta) err.meta = failFastError.meta;
        throw err;
      }
    }

    const result = await requestHealth(healthUrl, requestTimeoutMs);
    if (result.ok) {
      log.info('Container healthy');
      return;
    }

    lastStatus = result.statusCode;
    lastError = result.error;
    if (lastStatus) {
      log.debug(`Health check not ready (status ${lastStatus})`);
    } else if (lastError) {
      log.debug('Health check error (expected during startup):', lastError);
    }
    await sleep(intervalMs);
  }

  const err = new Error(
    `Container did not become healthy after ${Math.round(timeoutMs / 1000)}s` +
    (lastStatus ? ` (last status: ${lastStatus})` : '') +
    (lastError ? ` (last error: ${lastError})` : '')
  );
  err.code = 'HEALTH_TIMEOUT';
  err.meta = { attempts, timeoutMs, lastStatus, lastError };
  throw err;
}

module.exports = { waitUntilHealthy };
