import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { apiGet } from '../../core/api.js';

const REFRESH_INTERVAL_MS = 10 * 60 * 1000;
const JITTER_FACTOR = 0.15;

function jitteredInterval(baseMs) {
  const jitter = baseMs * JITTER_FACTOR * (2 * Math.random() - 1);
  return Math.max(1000, Math.round(baseMs + jitter));
}
const API_TIMEOUT_MS = 60000;
const BUCKET_KEYS = ['lt_6h', '6h_12h', '12h_24h', 'gt_24h'];

function normalizeBuckets(rawBuckets) {
  const buckets = {};
  for (const key of BUCKET_KEYS) {
    const value = Number(rawBuckets?.[key]);
    buckets[key] = Number.isFinite(value) ? value : 0;
  }
  return buckets;
}

function normalizeStation(rawStation) {
  const lots = Array.isArray(rawStation?.lots) ? rawStation.lots : [];
  return {
    specname: String(rawStation?.specname ?? '').trim(),
    spec_order: Number(rawStation?.spec_order ?? 999999),
    buckets: normalizeBuckets(rawStation?.buckets),
    total: Number(rawStation?.total ?? lots.length),
    lots,
  };
}

function normalizePayload(payload) {
  const stations = Array.isArray(payload?.stations)
    ? payload.stations.map(normalizeStation).filter((station) => station.specname)
    : [];

  return {
    cache_time: payload?.cache_time ?? null,
    stations,
  };
}

function toComparableWaitHours(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function useQcGateData() {
  const stations = ref([]);
  const cacheTime = ref(null);
  const loading = ref(true);
  const refreshing = ref(false);
  const refreshSuccess = ref(false);
  const refreshError = ref(false);
  const errorMessage = ref('');
  const lastFetchedAt = ref(null);

  let refreshTimer = null;
  let currentRequest = null;

  const allLots = computed(() => {
    const merged = [];
    for (const station of stations.value) {
      const stationLots = Array.isArray(station.lots) ? station.lots : [];
      merged.push(...stationLots);
    }
    return merged.sort(
      (left, right) => toComparableWaitHours(right.wait_hours) - toComparableWaitHours(left.wait_hours)
    );
  });

  const fetchData = async ({ background = false } = {}) => {
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
      const response = await apiGet('/api/qc-gate/summary', {
        timeout: API_TIMEOUT_MS,
        signal: currentRequest.signal,
      });

      const payload = response?.success ? response.data : response;
      const normalized = normalizePayload(payload || {});

      stations.value = normalized.stations;
      cacheTime.value = normalized.cache_time;
      lastFetchedAt.value = new Date();
      refreshSuccess.value = true;
      setTimeout(() => { refreshSuccess.value = false; }, 1500);
      return true;
    } catch (error) {
      if (error?.name === 'AbortError') {
        return false;
      }
      errorMessage.value = error?.message || '載入 QC-GATE 資料失敗';
      refreshError.value = true;
      return false;
    } finally {
      loading.value = false;
      refreshing.value = false;
    }
  };

  const stopAutoRefresh = () => {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  };

  const scheduleNextRefresh = () => {
    stopAutoRefresh();
    refreshTimer = setTimeout(() => {
      if (!document.hidden) {
        void fetchData({ background: true });
      }
      scheduleNextRefresh();
    }, jitteredInterval(REFRESH_INTERVAL_MS));
  };

  const startAutoRefresh = () => {
    scheduleNextRefresh();
  };

  const resetAutoRefresh = () => {
    startAutoRefresh();
  };

  const refreshNow = async () => {
    resetAutoRefresh();
    await fetchData({ background: true });
  };

  const handleVisibilityChange = () => {
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
