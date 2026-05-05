/// <reference types="vite/client" />

/**
 * App Version Check
 *
 * Compares `meta.app_version` from API responses to the version baked into
 * the current bundle at build time.  When a mismatch is detected the client
 * is warned (DEV: console.warn, PROD: optional callback) so users can be
 * prompted to refresh.
 */

// Version baked into the current bundle
const _BUNDLE_VERSION: string =
  (typeof import.meta !== 'undefined' && import.meta.env?.VITE_APP_VERSION) || 'unknown';

type VersionMismatchCallback = (serverVersion: string, bundleVersion: string) => void;

let _mismatchCallback: VersionMismatchCallback | null = null;
let _lastSeenServerVersion: string | null = null;
let _mismatchReported = false;

/**
 * Register a callback to be invoked on version mismatch.
 */
export function onVersionMismatch(cb: VersionMismatchCallback): void {
  _mismatchCallback = typeof cb === 'function' ? cb : null;
}

export interface AppVersionMeta {
  app_version?: string | null;
  [key: string]: unknown;
}

/**
 * Check the app_version in a response meta object against the bundle version.
 */
export function appVersionCheck(meta: AppVersionMeta | null | undefined): void {
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
 */
export function getLastSeenServerVersion(): string | null {
  return _lastSeenServerVersion;
}

/**
 * Return the bundle version string (baked in at build time).
 */
export function getBundleVersion(): string {
  return _BUNDLE_VERSION;
}

/**
 * Reset internal state (for testing only).
 */
export function _resetVersionCheck(): void {
  _mismatchReported = false;
  _lastSeenServerVersion = null;
  _mismatchCallback = null;
}
