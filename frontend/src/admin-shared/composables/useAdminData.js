import { ref, unref } from 'vue';

import { apiGet } from '../../core/api.js';

function resolveValue(value, fallback = undefined) {
  const resolved = unref(value);
  if (resolved === undefined || resolved === null) {
    return fallback;
  }
  return resolved;
}

function resolveErrorMessage(error, fallback = '載入失敗') {
  if (!error) return fallback;
  if (typeof error?.message === 'string' && error.message.trim()) {
    return error.message;
  }
  return fallback;
}

function createDataFetcher(fetcher, { initialData = null } = {}) {
  const data = ref(initialData);
  const loading = ref(false);
  const error = ref('');

  async function refresh() {
    loading.value = true;
    error.value = '';
    try {
      data.value = await fetcher();
      return data.value;
    } catch (err) {
      error.value = resolveErrorMessage(err);
      return null;
    } finally {
      loading.value = false;
    }
  }

  return {
    data,
    loading,
    error,
    refresh,
  };
}

function unwrapEnvelope(payload) {
  return payload?.data ?? payload ?? null;
}

export function useSystemStatus() {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/system-status');
    return unwrapEnvelope(response);
  });
}

export function useMetrics() {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/metrics');
    return unwrapEnvelope(response);
  });
}

export function usePerfDetail() {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/performance-detail');
    return unwrapEnvelope(response);
  });
}

export function usePerfHistory(minutes = 30, bucket = 30) {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/performance-history', {
      params: {
        minutes: resolveValue(minutes, 30),
        bucket: resolveValue(bucket, 30),
      },
    });
    const snapshots = response?.data?.snapshots || [];
    return snapshots.map((snapshot) => ({
      ...snapshot,
      worker_rss_mb: snapshot.worker_rss_bytes
        ? Math.round((snapshot.worker_rss_bytes / 1048576) * 10) / 10
        : 0,
      redis_used_memory_mb:
        snapshot.redis_used_memory_mb
        ?? (snapshot.redis_used_memory
          ? Math.round((snapshot.redis_used_memory / 1048576) * 10) / 10
          : 0),
    }));
  }, { initialData: [] });
}

export function useStorageInfo() {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/storage-info');
    return unwrapEnvelope(response);
  });
}

export function useUsageKpi(startDate, endDate, department) {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/user-usage-kpi', {
      params: {
        start_date: resolveValue(startDate, ''),
        end_date: resolveValue(endDate, ''),
        department: resolveValue(department, ''),
      },
    });
    return unwrapEnvelope(response);
  });
}

export function useLogs(level, q, limit = 50, offset = 0) {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/logs', {
      params: {
        level: resolveValue(level, ''),
        q: resolveValue(q, ''),
        limit: resolveValue(limit, 50),
        offset: resolveValue(offset, 0),
      },
    });
    return unwrapEnvelope(response);
  });
}

export function useHealthSummary() {
  return createDataFetcher(async () => {
    const response = await fetch('/health', {
      cache: 'no-store',
      credentials: 'same-origin',
    });

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const message = payload?.message || payload?.error || `HTTP ${response.status}`;
      throw new Error(message);
    }

    return payload || null;
  });
}
