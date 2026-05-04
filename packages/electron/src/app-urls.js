'use strict';

/**
 * Container WebUI is bound to 127.0.0.1:8787 (see docker-manager / integration).
 * Use 127.0.0.1 everywhere so Windows does not prefer ::1 and miss the mapped port.
 */
const APP_ORIGIN = 'http://127.0.0.1:8787';

module.exports = {
  APP_ORIGIN,
  APP_HOME_URL: `${APP_ORIGIN}/`,
  HEALTH_URL: `${APP_ORIGIN}/health`,
};
