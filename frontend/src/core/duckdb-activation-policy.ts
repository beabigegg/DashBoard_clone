/**
 * Shared activation policy for DuckDB-WASM local compute.
 *
 * Call checkLocalComputeEligibility() after a /query or /view response
 * to decide whether to activate browser-side view derivation.
 */

import { isDuckDBSupported } from './duckdb-client.js';

export interface LocalComputeEligibilityOptions {
  spoolDownloadUrl?: string | null;
  totalRowCount: number;
  threshold?: number;
  flagEnabled?: boolean;
}

export interface LocalComputeEligibilityResult {
  eligible: boolean;
  reason: string;
}

/**
 * Determine whether local DuckDB-WASM compute should be activated.
 */
export function checkLocalComputeEligibility({
  spoolDownloadUrl,
  totalRowCount,
  threshold = 5000,
  flagEnabled = true,
}: LocalComputeEligibilityOptions = { totalRowCount: 0 }): LocalComputeEligibilityResult {
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
