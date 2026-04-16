/**
 * App Version Check
 *
 * Compares `meta.app_version` from API responses to the version baked into
 * the current bundle at build time.  When a mismatch is detected the client
 * is warned (DEV: console.warn, PROD: optional callback) so users can be
 * prompted to refresh.
 *
 * Usage in api.js:
 *   import { appVersionCheck } from './app-version-check.js';
 *   // after each successful response:
 *   appVersionCheck(payload?.meta);
 *
 * The bundle version is read from import.meta.env.VITE_APP_VERSION (set at
 * build time via vite.config.js define: { __APP_VERSION__: ... }).
 * Falls back to 'unknown' if the env var is not defined.
 */

// Version baked into the current bundle
const _BUNDLE_VERSION =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_APP_VERSION) || 'unknown';

let _mismatchCallback = null;
let _lastSeenServerVersion = null;
let _mismatchReported = false;

/**
 * Register a callback to be invoked on version mismatch.
 *
 * @param {(serverVersion: string, bundleVersion: string) => void} cb
 */
export function onVersionMismatch(cb) {
  _mismatchCallback = typeof cb === 'function' ? cb : null;
}

/**
 * Check the app_version in a response meta object against the bundle version.
 *
 * - If bundle version is 'unknown', skip (can't compare reliably).
 * - If server version matches bundle, clear any prior mismatch state.
 * - If mismatch, fire the callback (once per page load unless reset).
 *
 * @param {object|null|undefined} meta - The `meta` field from an API response
 */
export function appVersionCheck(meta) {
  if (!meta || typeof meta !== 'object') return;

  const serverVersion = meta.app_version;
  if (!serverVersion || typeof serverVersion !== 'string') return;

  _lastSeenServerVersion = serverVersion;

  if (_BUNDLE_VERSION === 'unknown') return;

  if (serverVersion === _BUNDLE_VERSION) {
    _mismatchReported = false;
    return;
  }

  if (_mismatchReported) return;
  _mismatchReported = true;

  if (_mismatchCallback) {
    try {
      _mismatchCallback(serverVersion, _BUNDLE_VERSION);
    } catch {
      // callbacks must not crash the request path
    }
  } else if (typeof console !== 'undefined') {
    console.warn(
      `[app-version-check] Bundle version (${_BUNDLE_VERSION}) differs from server (${serverVersion}). ` +
        'Consider refreshing the page.'
    );
  }
}

/**
 * Return the last server version seen in an API response.
 * Returns null if no response has been processed yet.
 *
 * @returns {string|null}
 */
export function getLastSeenServerVersion() {
  return _lastSeenServerVersion;
}

/**
 * Return the bundle version string (baked in at build time).
 *
 * @returns {string}
 */
export function getBundleVersion() {
  return _BUNDLE_VERSION;
}

/**
 * Reset internal state (for testing only).
 */
export function _resetVersionCheck() {
  _mismatchReported = false;
  _lastSeenServerVersion = null;
  _mismatchCallback = null;
}
