/// <reference types="vite/client" />

import type { ApiResponse } from './types.js';

const DEFAULT_TIMEOUT = 90000;
const IS_DEV = typeof import.meta !== 'undefined' && Boolean(import.meta.env?.DEV);

// DEV-mode guard — no-op in production builds
let _guardResponse: ((url: string, data: unknown) => void) | null = null;
if (IS_DEV) {
  import('./dev-warnings.js').then((m) => {
    _guardResponse = m.guardResponse;
  }).catch(() => {});
}

// App-version check — lazy-loaded to avoid circular deps
// TODO: type this as AppVersionMeta once circular import is resolved
let _appVersionCheck: ((meta: unknown) => void) | null = null;
import('./app-version-check.js').then((m) => {
  _appVersionCheck = m.appVersionCheck as (meta: unknown) => void;
}).catch(() => {});

// ---------------------------------------------------------------------------
// Per-endpoint in-flight dedup
//
// Keyed by `method|url|bodyFingerprint`.  Concurrent calls with the same key
// share a single in-flight promise; subsequent callers resolve with the same
// result.  The entry is removed when the promise settles.
// ---------------------------------------------------------------------------
const _inFlight = new Map<string, Promise<unknown>>();

export interface FetchOptions extends RequestInit {
  timeout?: number;
  params?: Record<string, unknown>;
  signal?: AbortSignal;
  noDedup?: boolean;
  silent?: boolean;
  retries?: number;
}

// TODO: type MesApiBridge more precisely once the bridge contract is documented
interface MesApiBridge {
  __mesApiBridge?: boolean;
  get?: (url: string, options?: FetchOptions) => Promise<unknown>;
  post?: (url: string, payload: unknown, options?: FetchOptions) => Promise<unknown>;
}

declare global {
  interface Window {
    MesApi?: MesApiBridge;
    __MES_PORTAL_SHELL_NAVIGATE__?: (path: string, options?: { replace?: boolean }) => void;
  }
}

function getCsrfToken(): string {
  return (document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement)?.content || '';
}

function withCsrfHeaders(
  headers: Record<string, string> = {},
  method = 'GET'
): Record<string, string> {
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

interface ApiError extends Error {
  status: number;
  payload: unknown;
  errorCode: string | null;
  retryAfterSeconds: number | null;
}

function buildApiError(response: Response, payload: unknown): ApiError {
  const p = payload as Record<string, unknown> | null | undefined;
  const message =
    (p?.error as Record<string, unknown> | undefined)?.message as string ||
    (typeof p?.error === 'string' ? p.error : null) ||
    p?.message as string ||
    `HTTP ${response.status}`;

  const error = new Error(message) as ApiError;
  error.status = response.status;
  error.payload = payload;
  error.errorCode =
    ((p?.error as Record<string, unknown> | undefined)?.code as string) ||
    p?.code as string ||
    null;
  error.retryAfterSeconds = Number(
    (p?.meta as Record<string, unknown> | undefined)?.retry_after_seconds ||
    response.headers.get('Retry-After') ||
    0
  ) || null;
  return error;
}

function buildUrlWithParams(url: string, params: Record<string, unknown> | undefined): string {
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

function isExternalMesApiBridge(candidate: unknown): candidate is MesApiBridge {
  const c = candidate as MesApiBridge | null | undefined;
  return Boolean(c?.get) && !c?.__mesApiBridge;
}

interface AbortController_ {
  signal: AbortSignal;
  cleanup: () => void;
}

function createAbortSignal(
  timeoutMs: number,
  externalSignal: AbortSignal | undefined
): AbortController_ {
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  let onAbort: (() => void) | null = null;

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
 * Only deduplicates GET requests.  POST/PUT/PATCH/DELETE are mutations triggered
 * by user action and must never be deduplicated — sharing a single in-flight
 * promise across two POST calls means the second caller can receive an abort
 * signal (e.g. timeout) that originated from the first call's AbortController,
 * producing a misleading "signal is aborted without reason" error.
 */
function _buildDedupKey(method: string, url: string, _body: unknown): string | null {
  const m = String(method).toUpperCase();
  if (m === 'GET') return `GET|${url}|`;
  return null;
}

async function parseResponsePayload(response: Response): Promise<unknown> {
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

async function _fetchJsonRaw(
  requestUrl: string,
  fetchOptions: RequestInit,
  externalSignal: AbortSignal | undefined,
  timeout: number
): Promise<unknown> {
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
        _appVersionCheck((data as Record<string, unknown>)?.meta);
      } catch (_e) {
        // Must never crash the request path
      }
    }
    return data;
  } finally {
    cleanup();
  }
}

async function fetchJson(url: string, options: FetchOptions = {}): Promise<unknown> {
  const {
    timeout = DEFAULT_TIMEOUT,
    params,
    signal: externalSignal,
    noDedup = false,
    ...fetchOptions
  } = options;

  const requestUrl = buildUrlWithParams(url, params);
  const dedupKey = noDedup
    ? null
    : _buildDedupKey(fetchOptions.method || 'GET', requestUrl, fetchOptions.body);

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

export async function apiGet<T = unknown>(
  url: string,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  if (isExternalMesApiBridge(window.MesApi)) {
    return window.MesApi.get!(url, options) as Promise<ApiResponse<T>>;
  }
  return fetchJson(url, { ...options, method: 'GET' }) as Promise<ApiResponse<T>>;
}

export async function apiPost<T = unknown>(
  url: string,
  payload: unknown,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  if (isExternalMesApiBridge(window.MesApi) && window.MesApi?.post) {
    const enrichedOptions: FetchOptions = {
      ...options,
      headers: withCsrfHeaders(
        (options.headers || {}) as Record<string, string>,
        'POST'
      ),
    };
    return window.MesApi.post(url, payload, enrichedOptions) as Promise<ApiResponse<T>>;
  }

  return fetchJson(url, {
    ...options,
    method: 'POST',
    headers: withCsrfHeaders(
      {
        'Content-Type': 'application/json',
        ...((options.headers || {}) as Record<string, string>),
      },
      'POST'
    ),
    body: JSON.stringify(payload),
  }) as Promise<ApiResponse<T>>;
}

export async function apiUpload<T = unknown>(
  url: string,
  formData: FormData,
  options: FetchOptions = {}
): Promise<ApiResponse<T>> {
  if (isExternalMesApiBridge(window.MesApi) && window.MesApi?.post) {
    const enrichedOptions: FetchOptions = {
      ...options,
      headers: withCsrfHeaders(
        (options.headers || {}) as Record<string, string>,
        'POST'
      ),
    };
    return window.MesApi.post(url, formData, enrichedOptions) as Promise<ApiResponse<T>>;
  }

  return fetchJson(url, {
    ...options,
    method: 'POST',
    headers: withCsrfHeaders((options.headers || {}) as Record<string, string>, 'POST'),
    body: formData,
  }) as Promise<ApiResponse<T>>;
}

/**
 * Returns the current count of in-flight deduped requests (for testing only).
 */
export function _inFlightSize(): number {
  return _inFlight.size;
}

/**
 * Clear the in-flight dedup map (for testing only).
 */
export function _clearInFlight(): void {
  _inFlight.clear();
}

export function ensureMesApiAvailable(): MesApiBridge {
  if (window.MesApi) {
    return window.MesApi;
  }

  const bridge: MesApiBridge = {
    __mesApiBridge: true,
    get(url: string, options?: FetchOptions) {
      return fetchJson(url, { ...options, method: 'GET' });
    },
    post(url: string, payload: unknown, options: FetchOptions = {}) {
      const method = options.method || 'POST';
      const headers = withCsrfHeaders(
        {
          'Content-Type': 'application/json',
          ...((options.headers || {}) as Record<string, string>),
        },
        method
      );

      const body = payload instanceof FormData ? payload : JSON.stringify(payload);
      const normalizedHeaders =
        payload instanceof FormData
          ? withCsrfHeaders((options.headers || {}) as Record<string, string>, method)
          : headers;

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
