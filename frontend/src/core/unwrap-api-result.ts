/**
 * Shared utility for unwrapping standard API response envelopes.
 *
 * Canonical envelope shape:
 *   { success: true,  data: <payload>, meta: { timestamp, app_version, ... } }
 *   { success: false, error: { code, message }, meta: { ... } }
 *
 * Usage:
 *   const result = unwrapApiResult(response, 'fallback error message');
 *   // On success: returns the full envelope (access .data for payload)
 *   // On success===false: throws Error with error message
 *   // Legacy (no success field): returns the value as-is
 */

import type { ApiResponse } from './types.js';

export type { ApiResponse } from './types.js';

/**
 * Unwrap a standard API envelope response.
 *
 * @param result - The raw API response object
 * @param fallbackMessage - Error message to use if none found in response
 * @returns The full envelope (caller accesses .data for payload)
 * @throws Error When success===false, with the server error message
 */
export function unwrapApiResult<T = unknown>(
  result: ApiResponse<T> | null | undefined | Record<string, unknown>,
  fallbackMessage?: string
): ApiResponse<T> | null | undefined | Record<string, unknown> {
  if ((result as { success?: unknown })?.success === true) {
    // Return the full envelope — callers access .data for the payload
    return result;
  }

  if ((result as { success?: unknown })?.success === false) {
    const errorObj = (result as { error?: unknown }).error;
    const serverMessage =
      (typeof errorObj === 'object' && errorObj !== null
        ? (errorObj as { message?: unknown }).message
        : null) as string | null |undefined ||
      (typeof errorObj === 'string' ? errorObj : null) ||
      fallbackMessage ||
      'API request failed';
    throw new Error(String(serverMessage));
  }

  // Legacy: no success field (e.g., plain data or unknown shape)
  return result;
}

/**
 * Unwrap and extract the data payload directly.
 *
 * Convenience wrapper when you only need data and don't need meta.
 *
 * @param result - The raw API response object
 * @param fallbackMessage - Error message to use if none found in response
 * @returns The data payload (result.data) or the result itself for legacy responses
 * @throws Error When success===false
 */
export function unwrapApiData<T = unknown>(
  result: ApiResponse<T> | null | undefined | Record<string, unknown>,
  fallbackMessage?: string
): T | null | undefined | Record<string, unknown> {
  const envelope = unwrapApiResult<T>(result, fallbackMessage);
  // If envelope has a data field, return it; otherwise return the envelope itself
  if (envelope !== null && envelope !== undefined && 'data' in Object(envelope)) {
    return (envelope as { data: T }).data;
  }
  return envelope as null | undefined | Record<string, unknown>;
}
