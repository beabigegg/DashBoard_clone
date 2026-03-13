/**
 * Shared activation policy for DuckDB-WASM local compute.
 *
 * Call checkLocalComputeEligibility() after a /query or /view response
 * to decide whether to activate browser-side view derivation.
 */

import { isDuckDBSupported } from './duckdb-client.js';

/**
 * Determine whether local DuckDB-WASM compute should be activated.
 *
 * @param {object} opts
 * @param {string|null|undefined} opts.spoolDownloadUrl   - URL from server response
 * @param {number}                opts.totalRowCount       - Row count from server response
 * @param {number}               [opts.threshold=5000]    - Min rows to activate local mode
 * @param {boolean}              [opts.flagEnabled=true]  - Page-level feature flag
 * @returns {{ eligible: boolean, reason: string }}
 */
export function checkLocalComputeEligibility({
  spoolDownloadUrl,
  totalRowCount,
  threshold = 5000,
  flagEnabled = true,
} = {}) {
  if (!flagEnabled) {
    return { eligible: false, reason: 'flag_disabled' };
  }
  if (!isDuckDBSupported()) {
    return { eligible: false, reason: 'browser_unsupported' };
  }
  if (!spoolDownloadUrl) {
    return { eligible: false, reason: 'no_spool_url' };
  }
  if (Number(totalRowCount || 0) < threshold) {
    return { eligible: false, reason: 'below_threshold' };
  }
  return { eligible: true, reason: 'ok' };
}
