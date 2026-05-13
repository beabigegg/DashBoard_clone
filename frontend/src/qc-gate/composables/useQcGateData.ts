import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { apiGet } from '../../core/api';

const REFRESH_INTERVAL_MS = 10 * 60 * 1000;
const JITTER_FACTOR = 0.15;

function jitteredInterval(baseMs: number): number {
  const jitter = baseMs * JITTER_FACTOR * (2 * Math.random() - 1);
  return Math.max(1000, Math.round(baseMs + jitter));
}
const API_TIMEOUT_MS = 60000;
const BUCKET_KEYS = ['lt_6h', '6h_12h', '12h_24h', 'gt_24h'] as const;

export type BucketKey = (typeof BUCKET_KEYS)[number];

export interface BucketCounts {
  lt_6h: number;
  '6h_12h': number;
  '12h_24h': number;
  gt_24h: number;
}

export interface LotItem {
  lot_id: string;
  package: string;
  product: string;
  qty: number | string;
  step: string;
  workorder: string;
  move_in_time: string | null;
  wait_hours: number | string;
  bucket: BucketKey;
  status: string;
  [key: string]: unknown;
}

export interface StationData {
  specname: string;
  spec_order: number;
  buckets: BucketCounts;
  total: number;
  lots: LotItem[];
}

export interface ApiPayload {
  cache_time?: string | null;
  stations?: Array<Record<string, unknown>>;
}

function normalizeBuckets(rawBuckets: Record<string, unknown> | null | undefined): BucketCounts {
  const buckets = {} as BucketCounts;
  for (const key of BUCKET_KEYS) {
    const value = Number(rawBuckets?.[key]);
    buckets[key] = Number.isFinite(value) ? value : 0;
  }
  return buckets;
}

function normalizeStation(rawStation: Record<string, unknown> | null | undefined): StationData {
  const lots = Array.isArray(rawStation?.lots) ? (rawStation.lots as LotItem[]) : [];
  return {
    specname: String(rawStation?.specname ?? '').trim(),
    spec_order: Number(rawStation?.spec_order ?? 999999),
    buckets: normalizeBuckets(rawStation?.buckets as Record<string, unknown> | null | undefined),
    total: Number(rawStation?.total ?? lots.length),
    lots,
  };
}

function normalizePayload(payload: ApiPayload): { cache_time: string | null; stations: StationData[] } {
  const stations = Array.isArray(payload?.stations)
    ? payload.stations
        .map((s) => normalizeStation(s as Record<string, unknown>))
        .filter((station) => station.specname)
    : [];

  return {
    cache_time: payload?.cache_time ?? null,
    stations,
  };
}

function toComparableWaitHours(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function useQcGateData() {
  const stations = ref<StationData[]>([]);
  const cacheTime = ref<string | null>(null);
  const loading = ref<boolean>(true);
  const refreshing = ref<boolean>(false);
  const refreshSuccess = ref<boolean>(false);
  const refreshError = ref<boolean>(false);
  const errorMessage = ref<string>('');
  const lastFetchedAt = ref<Date | null>(null);

  let refreshTimer: ReturnType<typeof setTimeout> | null = null;
  let currentRequest: AbortController | null = null;

  const allLots = computed<LotItem[]>(() => {
    const merged: LotItem[] = [];
    for (const station of stations.value) {
      const stationLots = Array.isArray(station.lots) ? station.lots : [];
      merged.push(...stationLots);
    }
    return merged.sort(
      (left, right) => toComparableWaitHours(right.wait_hours) - toComparableWaitHours(left.wait_hours)
    );
  });

  const fetchData = async ({ background = false }: { background?: boolean } = {}): Promise<boolean> => {
    if (currentRequest) {
      currentRequest.abort();
    }

    currentRequest = new AbortController();

    if (background) {
      refreshing.value = true;
    } else {
      loading.value = true;
    }

    errorMessage.value = '';
    refreshError.value = false;

    try {
      const response = await apiGet<ApiPayload>('/api/qc-gate/summary', {
        timeout: API_TIMEOUT_MS,
        signal: currentRequest.signal,
      });

      const payload = response?.success ? response.data : (response as unknown as ApiPayload);
      const normalized = normalizePayload(payload || {});

      stations.value = normalized.stations;
      cacheTime.value = normalized.cache_time;
      lastFetchedAt.value = new Date();
      refreshSuccess.value = true;
      setTimeout(() => { refreshSuccess.value = false; }, 1500);
      return true;
    } catch (error) {
      if ((error as Error)?.name === 'AbortError') {
        return false;
      }
      errorMessage.value = (error as Error)?.message || '載入 QC-GATE 資料失敗';
      refreshError.value = true;
      return false;
    } finally {
      loading.value = false;
      refreshing.value = false;
    }
  };

  const stopAutoRefresh = (): void => {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  };

  const scheduleNextRefresh = (): void => {
    stopAutoRefresh();
    refreshTimer = setTimeout(() => {
      if (!document.hidden) {
        void fetchData({ background: true });
      }
      scheduleNextRefresh();
    }, jitteredInterval(REFRESH_INTERVAL_MS));
  };

  const startAutoRefresh = (): void => {
    scheduleNextRefresh();
  };

  const resetAutoRefresh = (): void => {
    startAutoRefresh();
  };

  const refreshNow = async (): Promise<void> => {
    resetAutoRefresh();
    await fetchData({ background: true });
  };

  const handleVisibilityChange = (): void => {
    if (document.hidden) {
      return;
    }
    void fetchData({ background: true });
    resetAutoRefresh();
  };

  onMounted(() => {
    void fetchData({ background: false });
    startAutoRefresh();
    document.addEventListener('visibilitychange', handleVisibilityChange);
  });

  onBeforeUnmount(() => {
    stopAutoRefresh();
    if (currentRequest) {
      currentRequest.abort();
      currentRequest = null;
    }
    document.removeEventListener('visibilitychange', handleVisibilityChange);
  });

  return {
    stations,
    cacheTime,
    loading,
    refreshing,
    refreshSuccess,
    refreshError,
    errorMessage,
    lastFetchedAt,
    allLots,
    fetchData,
    refreshNow,
    resetAutoRefresh,
  };
}
