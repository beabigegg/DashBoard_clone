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

const _warned = new Set<string>();

function _warn(key: string, msg: string): void {
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
 * @param pagination - The pagination object from API response
 * @param endpoint - Endpoint path for context
 */
export function detectNaNPagination(
  pagination: Record<string, unknown> | null | undefined,
  endpoint = 'unknown'
): void {
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
 * @param response - The raw API response
 * @param endpoint - Endpoint path for context
 */
export function detectUnknownEnvelope(response: unknown, endpoint = 'unknown'): void {
  if (!response || typeof response !== 'object') {
    _warn(
      `unknown-envelope:${endpoint}:null`,
      `Non-object response at ${endpoint}: ${typeof response}`
    );
    return;
  }

  const r = response as Record<string, unknown>;

  if (!('success' in r)) {
    _warn(
      `unknown-envelope:${endpoint}:no-success`,
      `Response missing 'success' field at ${endpoint} — may be legacy or malformed`
    );
  }

  if (!('meta' in r) && 'success' in r) {
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
 * @param endpoint - The API endpoint path (e.g. '/api/hold-overview/summary')
 * @param response - The full API response envelope
 */
export function guardResponse(endpoint: string, response: unknown): void {
  detectUnknownEnvelope(response, endpoint);

  const schema = ENDPOINT_SCHEMAS[endpoint];
  if (!schema) return;

  const r = response as Record<string, unknown> | null | undefined;
  const data = r?.data;
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
 * @param arr - The array to inspect
 * @param fieldPath - Dot-path label for context (e.g. 'data.items')
 * @param endpoint - Endpoint path for context
 */
export function detectArrayShape(arr: unknown, fieldPath = 'items', endpoint = 'unknown'): void {
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
 * @param spoolUrl - The spool_download_url from API response
 * @param endpoint - Endpoint path for context
 */
export function detectSpoolContentType(
  spoolUrl: string | null | undefined,
  endpoint = 'unknown'
): void {
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
 * @param data - The `data` field from an API response
 * @param endpoint - Endpoint path for context
 */
export function detectMissingSignal(data: unknown, endpoint = 'unknown'): void {
  if (!data || typeof data !== 'object') return;

  const d = data as Record<string, unknown>;

  // Only check async-style responses (those with async=true or status field)
  const looksAsync =
    d.async === true ||
    d.status === 'queued' ||
    d.status === 'running' ||
    d.job_id !== undefined;

  if (!looksAsync) return;

  const hasSignal = d.job_id || d.query_id || d.dataset_id;
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
export function _resetWarned(): void {
  _warned.clear();
}
