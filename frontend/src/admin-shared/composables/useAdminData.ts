import { ref, unref, type Ref, type MaybeRef } from 'vue';

import { apiGet } from '../../core/api';
import type { ApiResponse } from '../../core/types';

interface DataFetcher<T> {
  data: Ref<T | null>;
  loading: Ref<boolean>;
  error: Ref<string>;
  refresh: () => Promise<T | null>;
}

interface DataFetcherOptions<T> {
  initialData?: T | null;
}

function resolveValue<T>(value: MaybeRef<T | undefined | null>, fallback: T): T;
function resolveValue<T>(value: MaybeRef<T | undefined | null>, fallback?: undefined): T | undefined;
function resolveValue<T>(value: MaybeRef<T | undefined | null>, fallback?: T): T | undefined {
  const resolved = unref(value);
  if (resolved === undefined || resolved === null) {
    return fallback;
  }
  return resolved;
}

function resolveErrorMessage(error: unknown, fallback = '載入失敗'): string {
  if (!error) return fallback;
  if (
    typeof (error as { message?: unknown }).message === 'string' &&
    ((error as { message: string }).message).trim()
  ) {
    return (error as { message: string }).message;
  }
  return fallback;
}

function createDataFetcher<T>(
  fetcher: () => Promise<T>,
  { initialData = null }: DataFetcherOptions<T> = {}
): DataFetcher<T> {
  const data = ref<T | null>(initialData) as Ref<T | null>;
  const loading = ref(false);
  const error = ref('');

  async function refresh(): Promise<T | null> {
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

function unwrapEnvelope(payload: ApiResponse<unknown> | null | undefined): unknown {
  if (!payload) return null;
  if ('data' in payload) return payload.data ?? null;
  return null;
}

export function useSystemStatus(): DataFetcher<unknown> {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/system-status');
    return unwrapEnvelope(response);
  });
}

export function useMetrics(): DataFetcher<unknown> {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/metrics');
    return unwrapEnvelope(response);
  });
}

export function usePerfDetail(): DataFetcher<unknown> {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/performance-detail');
    return unwrapEnvelope(response);
  });
}

interface PerfSnapshot {
  ts?: string;
  worker_rss_bytes?: number;
  service_rss_bytes?: number;
  redis_used_memory_mb?: number;
  redis_used_memory?: number;
  worker_rss_mb?: number;
  service_rss_mb?: number;
  [key: string]: unknown;
}

export function usePerfHistory(
  minutes: MaybeRef<number | undefined> = 30,
  bucket: MaybeRef<number | undefined> = 30
): DataFetcher<PerfSnapshot[]> {
  return createDataFetcher(async () => {
    const response = await apiGet<{ snapshots?: PerfSnapshot[] }>('/admin/api/performance-history', {
      params: {
        minutes: resolveValue(minutes, 30),
        bucket: resolveValue(bucket, 30),
      },
    });
    const snapshots: PerfSnapshot[] = ('data' in response ? response.data?.snapshots : undefined) ?? [];
    return snapshots.map((snapshot) => ({
      ...snapshot,
      worker_rss_mb: snapshot.worker_rss_bytes
        ? Math.round((snapshot.worker_rss_bytes / 1048576) * 10) / 10
        : 0,
      service_rss_mb: snapshot.service_rss_bytes
        ? Math.round((snapshot.service_rss_bytes / 1048576) * 10) / 10
        : 0,
      redis_used_memory_mb:
        snapshot.redis_used_memory_mb
        ?? (snapshot.redis_used_memory
          ? Math.round((snapshot.redis_used_memory / 1048576) * 10) / 10
          : 0),
    }));
  }, { initialData: [] });
}

export function useStorageInfo(): DataFetcher<unknown> {
  return createDataFetcher(async () => {
    const response = await apiGet('/admin/api/storage-info');
    return unwrapEnvelope(response);
  });
}

export function useUsageKpi(
  startDate: MaybeRef<string | undefined>,
  endDate: MaybeRef<string | undefined>,
  department: MaybeRef<string | undefined>
): DataFetcher<unknown> {
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

export function useLogs(
  level: MaybeRef<string | undefined>,
  q: MaybeRef<string | undefined>,
  limit: MaybeRef<number | undefined> = 50,
  offset: MaybeRef<number | undefined> = 0
): DataFetcher<unknown> {
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

interface HealthPayload {
  message?: string;
  error?: string;
  [key: string]: unknown;
}

export function useHealthSummary(): DataFetcher<HealthPayload> {
  return createDataFetcher(async () => {
    const response = await fetch('/health', {
      cache: 'no-store',
      credentials: 'same-origin',
    });

    let payload: HealthPayload | null = null;
    try {
      payload = await response.json() as HealthPayload;
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const message = payload?.message || payload?.error || `HTTP ${response.status}`;
      throw new Error(message);
    }

    return payload ?? {};
  });
}
