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
