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

/**
 * Unwrap a standard API envelope response.
 *
 * @param {object} result - The raw API response object
 * @param {string} [fallbackMessage] - Error message to use if none found in response
 * @returns {object} The full envelope (caller accesses .data for payload)
 * @throws {Error} When success===false, with the server error message
 */
export function unwrapApiResult(result, fallbackMessage) {
  if (result?.success === true) {
    // Return the full envelope — callers access .data for the payload
    return result;
  }

  if (result?.success === false) {
    const serverMessage =
      result.error?.message ||
      (typeof result.error === 'string' ? result.error : null) ||
      fallbackMessage ||
      'API request failed';
    throw new Error(serverMessage);
  }

  // Legacy: no success field (e.g., plain data or unknown shape)
  return result;
}

/**
 * Unwrap and extract the data payload directly.
 *
 * Convenience wrapper when you only need data and don't need meta.
 *
 * @param {object} result - The raw API response object
 * @param {string} [fallbackMessage] - Error message to use if none found in response
 * @returns {*} The data payload (result.data) or the result itself for legacy responses
 * @throws {Error} When success===false
 */
export function unwrapApiData(result, fallbackMessage) {
  const envelope = unwrapApiResult(result, fallbackMessage);
  // If envelope has a data field, return it; otherwise return the envelope itself
  if (envelope !== null && envelope !== undefined && 'data' in Object(envelope)) {
    return envelope.data;
  }
  return envelope;
}
