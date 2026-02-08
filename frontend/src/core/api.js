const DEFAULT_TIMEOUT = 30000;

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

async function fetchJson(url, options = {}) {
  const timeout = options.timeout ?? DEFAULT_TIMEOUT;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });

    const data = await response.json();
    if (!response.ok) {
      throw buildApiError(response, data);
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

export async function apiGet(url, options = {}) {
  if (window.MesApi?.get) {
    return window.MesApi.get(url, options);
  }
  return fetchJson(url, { ...options, method: 'GET' });
}

export async function apiPost(url, payload, options = {}) {
  if (window.MesApi?.post) {
    return window.MesApi.post(url, payload, options);
  }
  return fetchJson(url, {
    ...options,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    body: JSON.stringify(payload)
  });
}

export async function apiUpload(url, formData, options = {}) {
  return fetchJson(url, {
    ...options,
    method: 'POST',
    body: formData
  });
}

export function ensureMesApiAvailable() {
  if (window.MesApi) {
    return window.MesApi;
  }

  const bridge = {
    get: (url, options) => apiGet(url, options),
    post: (url, payload, options) => apiPost(url, payload, options)
  };
  window.MesApi = bridge;
  return bridge;
}
