'use strict';

/**
 * Container WebUI is bound to 127.0.0.1:8787 (see docker-manager / integration).
 * Use 127.0.0.1 everywhere so Windows does not prefer ::1 and miss the mapped port.
 */
const APP_ORIGIN = 'http://127.0.0.1:8787';

module.exports = {
  APP_ORIGIN,
  APP_HOME_URL: `${APP_ORIGIN}/`,
  /** Fox first-run wizard (task 05b) — not the Hermes WebUI root onboarding. */
  APP_SETUP_URL: `${APP_ORIGIN}/setup`,
  HEALTH_URL: `${APP_ORIGIN}/health`,
};
