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
    function isRetryable(error, response) {
        // Network errors are retryable
        if (error && error.name === 'TypeError') {
            return true;
        }
        // Timeout is retryable
        if (error && error.name === 'TimeoutError') {
            return true;
        }
        // 5xx errors are retryable
        if (response && response.status >= 500) {
            return true;
        }
        // 4xx errors are NOT retryable
        if (response && response.status >= 400 && response.status < 500) {
            return false;
        }
        return true;
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

                    const data = await response.json();
                    return data;
                }

                // Non-OK response
                const errorData = await response.json().catch(() => ({}));
                const error = new Error(errorData.error || `HTTP ${response.status}`);
                error.status = response.status;
                error.data = errorData;

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

                lastError = error;
            }

            // Check if we should retry
            if (attempt < maxRetries && isRetryable(lastError, lastResponse)) {
                const delay = RETRY_DELAYS[attempt] || RETRY_DELAYS[RETRY_DELAYS.length - 1];
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
