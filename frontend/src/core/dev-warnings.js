/**
 * DEV-mode warning detectors for API response quality.
 *
 * All detectors are no-ops in production (import.meta.env.PROD check).
 * In DEV mode, they write to console.warn with a de-dup mechanism
 * (each unique key fires at most once per session, unless verbose mode is on).
 *
 * Enable verbose mode:
 *   localStorage.setItem('schema-guard-verbose', '1')
 */

import { assertShape } from './schema-guard.js';
import { ENDPOINT_SCHEMAS } from './endpoint-schemas.js';

const _warned = new Set();

function _warn(key, msg) {
  const verbose =
    typeof localStorage !== 'undefined' && localStorage.getItem('schema-guard-verbose') === '1';
  if (verbose || !_warned.has(key)) {
    _warned.add(key);
    console.warn(`[dev-warnings] ${msg}`);
  }
}

/**
 * Detect NaN in pagination fields and warn.
 *
 * Common source: Number(payload?.pagination?.page) when page is undefined.
 *
 * @param {object} pagination - The pagination object from API response
 * @param {string} [endpoint] - Endpoint path for context
 */
export function detectNaNPagination(pagination, endpoint = 'unknown') {
  if (!pagination || typeof pagination !== 'object') return;

  const numericFields = ['page', 'per_page', 'total', 'total_pages'];
  for (const field of numericFields) {
    const val = pagination[field];
    if (val !== undefined && (isNaN(Number(val)) || typeof val !== 'number')) {
      _warn(
        `nan-pagination:${endpoint}:${field}`,
        `NaN/non-numeric pagination.${field} detected at ${endpoint}: ${JSON.stringify(val)}`
      );
    }
  }
}

/**
 * Detect unknown envelope shape (missing success/data/meta fields).
 *
 * @param {*} response - The raw API response
 * @param {string} [endpoint] - Endpoint path for context
 */
export function detectUnknownEnvelope(response, endpoint = 'unknown') {
  if (!response || typeof response !== 'object') {
    _warn(
      `unknown-envelope:${endpoint}:null`,
      `Non-object response at ${endpoint}: ${typeof response}`
    );
    return;
  }

  if (!('success' in response)) {
    _warn(
      `unknown-envelope:${endpoint}:no-success`,
      `Response missing 'success' field at ${endpoint} — may be legacy or malformed`
    );
  }

  if (!('meta' in response) && 'success' in response) {
    _warn(
      `unknown-envelope:${endpoint}:no-meta`,
      `Response missing 'meta' field at ${endpoint}`
    );
  }
}

/**
 * Guard a response against the registered schema for the given endpoint.
 *
 * Calls assertShape on the data payload. Emits console.warn on mismatch.
 * No-op if no schema is registered for the endpoint.
 *
 * @param {string} endpoint - The API endpoint path (e.g. '/api/hold-overview/summary')
 * @param {object} response - The full API response envelope
 */
export function guardResponse(endpoint, response) {
  detectUnknownEnvelope(response, endpoint);

  const schema = ENDPOINT_SCHEMAS[endpoint];
  if (!schema) return;

  const data = response?.data;
  if (data === undefined || data === null) {
    _warn(
      `guard:${endpoint}:null-data`,
      `guardResponse: response.data is ${data} for ${endpoint}`
    );
    return;
  }

  assertShape(data, schema, `${endpoint}.data`);
}

/**
 * Detect array fields that contain non-object items or unexpected primitive shapes.
 *
 * @param {Array} arr - The array to inspect
 * @param {string} [fieldPath] - Dot-path label for context (e.g. 'data.items')
 * @param {string} [endpoint] - Endpoint path for context
 */
export function detectArrayShape(arr, fieldPath = 'items', endpoint = 'unknown') {
  if (!Array.isArray(arr)) {
    _warn(
      `array-shape:${endpoint}:${fieldPath}:not-array`,
      `detectArrayShape: expected Array at ${fieldPath} but got ${typeof arr} at ${endpoint}`
    );
    return;
  }

  if (arr.length === 0) return;

  const firstItemType = typeof arr[0];
  if (firstItemType !== 'object' || arr[0] === null) {
    _warn(
      `array-shape:${endpoint}:${fieldPath}:primitive`,
      `detectArrayShape: ${fieldPath}[0] is ${firstItemType} (not object) at ${endpoint} — check API shape`
    );
  }
}

/**
 * Detect spool download URLs with unexpected content-type hints.
 *
 * Spool URLs are expected to be parquet or CSV.  Warn if the URL suggests
 * a different format (e.g. JSON, XML) which would break the download handler.
 *
 * @param {string|null|undefined} spoolUrl - The spool_download_url from API response
 * @param {string} [endpoint] - Endpoint path for context
 */
export function detectSpoolContentType(spoolUrl, endpoint = 'unknown') {
  if (!spoolUrl) return;
  if (typeof spoolUrl !== 'string') {
    _warn(
      `spool-content-type:${endpoint}:non-string`,
      `detectSpoolContentType: spool_download_url is not a string at ${endpoint}: ${typeof spoolUrl}`
    );
    return;
  }

  const lower = spoolUrl.toLowerCase();
  const EXPECTED_EXTS = ['.parquet', '.csv', '.ndjson', '.gz'];
  const hasExpectedExt = EXPECTED_EXTS.some((ext) => lower.includes(ext));

  if (!hasExpectedExt && !lower.includes('/spool/') && !lower.includes('download')) {
    _warn(
      `spool-content-type:${endpoint}:unknown-format`,
      `detectSpoolContentType: spool_download_url may not be a recognised spool format at ${endpoint}: ${spoolUrl}`
    );
  }
}

/**
 * Detect async job responses missing the expected polling signal fields.
 *
 * When a 202 async response is returned, the client expects either
 * `job_id` (for job-based polling) or `query_id` (for spool-based polling).
 * Warn if neither is present.
 *
 * @param {object} data - The `data` field from an API response
 * @param {string} [endpoint] - Endpoint path for context
 */
export function detectMissingSignal(data, endpoint = 'unknown') {
  if (!data || typeof data !== 'object') return;

  // Only check async-style responses (those with async=true or status field)
  const looksAsync =
    data.async === true ||
    data.status === 'queued' ||
    data.status === 'running' ||
    data.job_id !== undefined;

  if (!looksAsync) return;

  const hasSignal = data.job_id || data.query_id || data.dataset_id;
  if (!hasSignal) {
    _warn(
      `missing-signal:${endpoint}`,
      `detectMissingSignal: async response at ${endpoint} has no job_id, query_id, or dataset_id — client cannot poll`
    );
  }
}

/**
 * Reset warned set (for testing only).
 */
export function _resetWarned() {
  _warned.clear();
}
