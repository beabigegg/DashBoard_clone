/**
 * MES API Client
 *
 * Unified API client with timeout, retry, and cancellation support.
 *
 * Usage:
 *   const data = await MesApi.get('/api/wip/summary');
 *   const data = await MesApi.post('/api/query_table', { table_name: 'xxx' });
 *
 *   // With options
 *   const data = await MesApi.get('/api/xxx', {
 *       params: { page: 1 },
 *       timeout: 60000,
 *       retries: 5,
 *       signal: abortController.signal,
 *       silent: true
 *   });
 */
const MesApi = (function() {
    'use strict';

    const DEFAULT_TIMEOUT = 30000;  // 30 seconds
    const DEFAULT_RETRIES = 3;
    const RETRY_DELAYS = [1000, 2000, 4000];  // exponential backoff
    const DEGRADED_CODES = new Set([
        'DB_POOL_EXHAUSTED',
        'CIRCUIT_BREAKER_OPEN',
        'SERVICE_UNAVAILABLE'
    ]);
    const POOL_EXHAUSTED_MAX_RETRIES = 0;  // fail fast to avoid thundering herd
    const CIRCUIT_OPEN_MAX_RETRIES = 1;
    const MIN_DEGRADED_DELAY_MS = 3000;

    let requestCounter = 0;

    /**
     * Generate a unique request ID
     */
    function generateRequestId() {
        const id = (++requestCounter).toString(36);
        return `req_${id.padStart(4, '0')}`;
    }

    /**
     * Build URL with query parameters
     */
    function buildUrl(url, params) {
        if (!params || Object.keys(params).length === 0) {
            return url;
        }
        const searchParams = new URLSearchParams();
        for (const [key, value] of Object.entries(params)) {
            if (value !== undefined && value !== null) {
                searchParams.append(key, value);
            }
        }
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}${searchParams.toString()}`;
    }

    /**
     * Check if error is retryable
     */
    function isRetryable(error, response, attempt, maxRetries) {
        if (!error) return false;

        // Network errors are retryable
        if (error && error.name === 'TypeError') {
            return attempt < maxRetries;
        }
        // Timeout is retryable
        if (error && error.name === 'TimeoutError') {
            return attempt < maxRetries;
        }
        // User abort or parse errors should never retry
        if (error.isUserAbort || error.isParseError) {
            return false;
        }

        // Degraded response handling with stricter retry policies
        if (error.errorCode === 'DB_POOL_EXHAUSTED') {
            return attempt < Math.min(maxRetries, POOL_EXHAUSTED_MAX_RETRIES);
        }
        if (error.errorCode === 'CIRCUIT_BREAKER_OPEN') {
            return attempt < Math.min(maxRetries, CIRCUIT_OPEN_MAX_RETRIES);
        }

        // Respect HTTP Retry-After when server explicitly asks for backoff
        if (error.retryAfterSeconds && (response?.status === 429 || response?.status === 503)) {
            return attempt < maxRetries;
        }

        // 5xx errors are retryable
        if (response && response.status >= 500) {
            return attempt < maxRetries;
        }
        // 4xx errors are NOT retryable
        if (response && response.status >= 400 && response.status < 500) {
            return false;
        }
        return attempt < maxRetries;
    }

    function parseRetryAfterSeconds(response, errorData) {
        const headerValue = response?.headers?.get?.('Retry-After');
        if (headerValue) {
            const parsed = Number(headerValue);
            if (!Number.isNaN(parsed) && parsed > 0) {
                return parsed;
            }
        }
        const metaRetry = errorData?.meta?.retry_after_seconds;
        const parsedMeta = Number(metaRetry);
        if (!Number.isNaN(parsedMeta) && parsedMeta > 0) {
            return parsedMeta;
        }
        return null;
    }

    function getErrorCode(errorData) {
        return errorData?.error?.code || errorData?.code || null;
    }

    function getErrorMessage(errorData, fallbackStatus) {
        if (errorData?.error?.message) return errorData.error.message;
        if (errorData?.error && typeof errorData.error === 'string') return errorData.error;
        if (errorData?.message) return errorData.message;
        return `HTTP ${fallbackStatus}`;
    }

    function getRetryDelayMs(error, attempt) {
        const baseDelay = RETRY_DELAYS[attempt] || RETRY_DELAYS[RETRY_DELAYS.length - 1];
        const retryAfterMs = error?.retryAfterSeconds ? error.retryAfterSeconds * 1000 : 0;

        if (error?.errorCode && DEGRADED_CODES.has(error.errorCode)) {
            return Math.max(baseDelay, retryAfterMs, MIN_DEGRADED_DELAY_MS);
        }
        if (retryAfterMs > 0) {
            return Math.max(baseDelay, retryAfterMs);
        }
        return baseDelay;
    }

    /**
     * Sleep for a given duration
     */
    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * Execute fetch with timeout
     */
    async function fetchWithTimeout(url, fetchOptions, timeout, externalSignal) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);

        // Link external signal if provided
        if (externalSignal) {
            if (externalSignal.aborted) {
                controller.abort();
            } else {
                externalSignal.addEventListener('abort', () => controller.abort());
            }
        }

        try {
            const response = await fetch(url, {
                ...fetchOptions,
                signal: controller.signal
            });
            clearTimeout(timeoutId);
            return response;
        } catch (error) {
            clearTimeout(timeoutId);
            // Distinguish between timeout and user abort
            if (error.name === 'AbortError') {
                if (externalSignal && externalSignal.aborted) {
                    error.isUserAbort = true;
                } else {
                    // Timeout
                    const timeoutError = new Error('Request timeout');
                    timeoutError.name = 'TimeoutError';
                    throw timeoutError;
                }
            }
            throw error;
        }
    }

    /**
     * Core request function with retry logic
     */
    async function request(method, url, options = {}) {
        const reqId = generateRequestId();
        const timeout = options.timeout || DEFAULT_TIMEOUT;
        const maxRetries = options.retries !== undefined ? options.retries : DEFAULT_RETRIES;
        const silent = options.silent || false;
        const signal = options.signal;

        const fullUrl = buildUrl(url, options.params);
        const startTime = Date.now();

        console.log(`[MesApi] ${reqId} ${method} ${fullUrl}`);

        const fetchOptions = {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };

        if (options.body) {
            fetchOptions.body = JSON.stringify(options.body);
        }

        let lastError = null;
        let lastResponse = null;
        let loadingToastId = null;

        for (let attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                // Check if already aborted
                if (signal && signal.aborted) {
                    console.log(`[MesApi] ${reqId} ⊘ Aborted`);
                    const abortError = new Error('Request aborted');
                    abortError.name = 'AbortError';
                    abortError.isUserAbort = true;
                    throw abortError;
                }

                const response = await fetchWithTimeout(fullUrl, fetchOptions, timeout, signal);
                lastResponse = response;

                if (response.ok) {
                    const elapsed = Date.now() - startTime;
                    console.log(`[MesApi] ${reqId} ✓ ${response.status} (${elapsed}ms)`);

                    // Dismiss loading toast if showing retry status
                    if (loadingToastId) {
                        Toast.dismiss(loadingToastId);
                    }

                    try {
                        const data = await response.json();
                        return data;
                    } catch (parseError) {
                        // JSON parse error on successful response - don't retry
                        console.error(`[MesApi] ${reqId} ✗ JSON parse failed:`, parseError.message);
                        if (!silent) {
                            Toast.error('回應資料解析失敗，資料量可能過大');
                        }
                        parseError.isParseError = true;
                        throw parseError;
                    }
                }

                // Non-OK response
                const errorData = await response.json().catch(() => ({}));
                const error = new Error(getErrorMessage(errorData, response.status));
                error.status = response.status;
                error.data = errorData;
                error.errorCode = getErrorCode(errorData);
                error.retryAfterSeconds = parseRetryAfterSeconds(response, errorData);

                // 4xx errors - don't retry
                if (response.status >= 400 && response.status < 500) {
                    console.log(`[MesApi] ${reqId} ✗ ${response.status} (no retry)`);
                    if (!silent) {
                        Toast.error(`請求錯誤: ${error.message}`);
                    }
                    throw error;
                }

                // 5xx errors - will retry
                lastError = error;

            } catch (error) {
                // User abort - don't retry, no toast
                if (error.isUserAbort) {
                    console.log(`[MesApi] ${reqId} ⊘ Aborted`);
                    if (loadingToastId) {
                        Toast.dismiss(loadingToastId);
                    }
                    throw error;
                }

                // JSON parse error on successful response - don't retry
                if (error.isParseError) {
                    if (loadingToastId) {
                        Toast.dismiss(loadingToastId);
                    }
                    throw error;
                }

                lastError = error;
            }

            // Check if we should retry
            if (attempt < maxRetries && isRetryable(lastError, lastResponse, attempt, maxRetries)) {
                const delay = getRetryDelayMs(lastError, attempt);
                console.log(`[MesApi] ${reqId} ✗ Retry ${attempt + 1}/${maxRetries} in ${delay}ms`);

                if (!silent) {
                    const retryMsg = `正在重試 (${attempt + 1}/${maxRetries})...`;
                    if (loadingToastId) {
                        Toast.update(loadingToastId, { message: retryMsg });
                    } else {
                        loadingToastId = Toast.loading(retryMsg);
                    }
                }

                await sleep(delay);
            }
        }

        // All retries exhausted
        const elapsed = Date.now() - startTime;
        console.log(`[MesApi] ${reqId} ✗ Failed after ${maxRetries} retries (${elapsed}ms)`);

        // Update or dismiss loading toast, show error with retry button
        if (loadingToastId) {
            Toast.dismiss(loadingToastId);
        }

        if (!silent) {
            const errorMsg = lastError.message || '請求失敗';
            Toast.error(`${errorMsg}`, {
                retry: () => request(method, url, options)
            });
        }

        throw lastError;
    }

    // Public API
    return {
        /**
         * Send a GET request
         * @param {string} url - The URL to request
         * @param {Object} options - Request options
         * @param {Object} options.params - URL query parameters
         * @param {number} options.timeout - Timeout in ms (default: 30000)
         * @param {number} options.retries - Max retries (default: 3)
         * @param {AbortSignal} options.signal - AbortController signal
         * @param {boolean} options.silent - Suppress toast notifications
         * @returns {Promise<any>} Response data
         */
        get: function(url, options = {}) {
            return request('GET', url, options);
        },

        /**
         * Send a POST request
         * @param {string} url - The URL to request
         * @param {Object} data - Request body data
         * @param {Object} options - Request options (same as get)
         * @returns {Promise<any>} Response data
         */
        post: function(url, data, options = {}) {
            return request('POST', url, { ...options, body: data });
        }
    };
})();
