const DEFAULT_TIMEOUT = 90000;
const IS_DEV = typeof import.meta !== 'undefined' && Boolean(import.meta.env?.DEV);

// DEV-mode guard — no-op in production builds
let _guardResponse = null;
if (IS_DEV) {
  import('./dev-warnings.js').then((m) => {
    _guardResponse = m.guardResponse;
  }).catch(() => {});
}

// App-version check — lazy-loaded to avoid circular deps
let _appVersionCheck = null;
import('./app-version-check.js').then((m) => {
  _appVersionCheck = m.appVersionCheck;
}).catch(() => {});

// ---------------------------------------------------------------------------
// Per-endpoint in-flight dedup
//
// Keyed by `method|url|bodyFingerprint`.  Concurrent calls with the same key
// share a single in-flight promise; subsequent callers resolve with the same
// result.  The entry is removed when the promise settles.
// ---------------------------------------------------------------------------
const _inFlight = new Map();

function getCsrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

function withCsrfHeaders(headers = {}, method = 'GET') {
  const normalized = String(method).toUpperCase();
  const merged = { ...headers };
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(normalized)) {
    const csrf = getCsrfToken();
    if (csrf && !merged['X-CSRF-Token']) {
      merged['X-CSRF-Token'] = csrf;
    }
  }
  return merged;
}

function buildApiError(response, payload) {
  const message =
    payload?.error?.message ||
    (typeof payload?.error === 'string' ? payload.error : null) ||
    payload?.message ||
    `HTTP ${response.status}`;

  const error = new Error(message);
  error.status = response.status;
  error.payload = payload;
  error.errorCode = payload?.error?.code || payload?.code || null;
  error.retryAfterSeconds = Number(
    payload?.meta?.retry_after_seconds || response.headers.get('Retry-After') || 0
  ) || null;
  return error;
}

function buildUrlWithParams(url, params) {
  if (!params || typeof params !== 'object') {
    return url;
  }

  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return;
    }

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== null && item !== undefined && item !== '') {
          searchParams.append(key, String(item));
        }
      });
      return;
    }

    searchParams.append(key, String(value));
  });

  const query = searchParams.toString();
  if (!query) {
    return url;
  }

  return url.includes('?') ? `${url}&${query}` : `${url}?${query}`;
}

function isExternalMesApiBridge(candidate) {
  return Boolean(candidate?.get) && !candidate.__mesApiBridge;
}

function createAbortSignal(timeoutMs, externalSignal) {
  const controller = new AbortController();
  let timeoutId = null;
  let onAbort = null;

  if (Number.isFinite(timeoutMs) && timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      controller.abort();
    }, timeoutMs);
  }

  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      onAbort = () => controller.abort();
      externalSignal.addEventListener('abort', onAbort, { once: true });
    }
  }

  return {
    signal: controller.signal,
    cleanup() {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      if (externalSignal && onAbort) {
        externalSignal.removeEventListener('abort', onAbort);
      }
    },
  };
}

/**
 * Build a dedup key for an in-flight request.
 *
 * Only deduplicates GET requests and safe POST requests where body is a plain
 * JSON object.  Non-deduplicable requests (FormData, streaming) return null.
 *
 * @param {string} method
 * @param {string} url
 * @param {*} body
 * @returns {string|null}
 */
function _buildDedupKey(method, url, body) {
  const m = String(method).toUpperCase();
  if (m === 'GET') return `GET|${url}|`;

  if (m === 'POST' && body && typeof body === 'string') {
    // body is JSON.stringify'd payload — use it as fingerprint directly
    return `POST|${url}|${body}`;
  }
  return null;
}

async function parseResponsePayload(response) {
  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    return response.json();
  }

  const rawText = await response.text();
  try {
    return JSON.parse(rawText);
  } catch {
    return { message: rawText };
  }
}

async function _fetchJsonRaw(requestUrl, fetchOptions, externalSignal, timeout) {
  const { signal, cleanup } = createAbortSignal(timeout, externalSignal);

  try {
    const response = await fetch(requestUrl, {
      ...fetchOptions,
      signal,
    });

    const data = await parseResponsePayload(response);
    if (!response.ok) {
      throw buildApiError(response, data);
    }
    // DEV-mode: validate envelope shape against registered schemas
    if (_guardResponse) {
      try {
        _guardResponse(requestUrl, data);
      } catch (_e) {
        // Guard must never throw in production path
      }
    }
    // App-version check
    if (_appVersionCheck) {
      try {
        _appVersionCheck(data?.meta);
      } catch (_e) {
        // Must never crash the request path
      }
    }
    return data;
  } finally {
    cleanup();
  }
}

async function fetchJson(url, options = {}) {
  const {
    timeout = DEFAULT_TIMEOUT,
    params,
    signal: externalSignal,
    noDedup = false,
    ...fetchOptions
  } = options;

  const requestUrl = buildUrlWithParams(url, params);
  const dedupKey = noDedup ? null : _buildDedupKey(fetchOptions.method || 'GET', requestUrl, fetchOptions.body);

  if (dedupKey) {
    const existing = _inFlight.get(dedupKey);
    if (existing) return existing;

    const promise = _fetchJsonRaw(requestUrl, fetchOptions, externalSignal, timeout).finally(() => {
      _inFlight.delete(dedupKey);
    });
    _inFlight.set(dedupKey, promise);
    return promise;
  }

  return _fetchJsonRaw(requestUrl, fetchOptions, externalSignal, timeout);
}

export async function apiGet(url, options = {}) {
  if (isExternalMesApiBridge(window.MesApi)) {
    return window.MesApi.get(url, options);
  }
  return fetchJson(url, { ...options, method: 'GET' });
}

export async function apiPost(url, payload, options = {}) {
  if (isExternalMesApiBridge(window.MesApi) && window.MesApi?.post) {
    const enrichedOptions = {
      ...options,
      headers: withCsrfHeaders(options.headers || {}, 'POST'),
    };
    return window.MesApi.post(url, payload, enrichedOptions);
  }

  return fetchJson(url, {
    ...options,
    method: 'POST',
    headers: withCsrfHeaders(
      {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      'POST'
    ),
    body: JSON.stringify(payload),
  });
}

export async function apiUpload(url, formData, options = {}) {
  if (isExternalMesApiBridge(window.MesApi) && window.MesApi?.post) {
    const enrichedOptions = {
      ...options,
      headers: withCsrfHeaders(options.headers || {}, 'POST'),
    };
    return window.MesApi.post(url, formData, enrichedOptions);
  }

  return fetchJson(url, {
    ...options,
    method: 'POST',
    headers: withCsrfHeaders(options.headers || {}, 'POST'),
    body: formData,
  });
}

/**
 * Returns the current count of in-flight deduped requests (for testing only).
 * @returns {number}
 */
export function _inFlightSize() {
  return _inFlight.size;
}

/**
 * Clear the in-flight dedup map (for testing only).
 */
export function _clearInFlight() {
  _inFlight.clear();
}

export function ensureMesApiAvailable() {
  if (window.MesApi) {
    return window.MesApi;
  }

  const bridge = {
    __mesApiBridge: true,
    get(url, options) {
      return fetchJson(url, { ...options, method: 'GET' });
    },
    post(url, payload, options = {}) {
      const method = options.method || 'POST';
      const headers = withCsrfHeaders(
        {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
        method
      );

      const body = payload instanceof FormData ? payload : JSON.stringify(payload);
      const normalizedHeaders = payload instanceof FormData ? withCsrfHeaders(options.headers || {}, method) : headers;

      return fetchJson(url, {
        ...options,
        method,
        headers: normalizedHeaders,
        body,
      });
    },
  };

  window.MesApi = bridge;
  return bridge;
}
