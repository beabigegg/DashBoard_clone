// @vitest-environment jsdom
/**
 * Unit tests for CacheTab.vue and PerformanceTab.vue — performance-detail new fields
 *
 * Change: admin-perf-detail-ui
 * AC-1: evicted_keys, expired_keys integers rendered
 * AC-2: mem_fragmentation_ratio ≤2 decimal places
 * AC-3a/b/c: slowlog entry list / null / empty placeholders
 * AC-4: temp_dir_bytes human-readable
 * AC-5a/b: memory_limit_state string / null placeholder
 * AC-6: all new fields null → no error, siblings intact
 * AC-7: existing fields do not regress
 *
 * Mock path note: test lives at src/admin-dashboard/tabs/__tests__/
 * Relative paths to src/ level require ../../../ (3 levels up).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref, defineComponent } from 'vue';

// ---------------------------------------------------------------------------
// Stub heavy components — paths relative to THIS test file location
// ---------------------------------------------------------------------------
vi.mock('../../../admin-shared/components/GaugeBar.vue', () => ({
  default: defineComponent({ name: 'GaugeBar', props: ['label', 'value', 'max', 'displayText'], template: '<div class="gauge-bar-stub" />' }),
}));
vi.mock('../../../admin-shared/components/TrendChart.vue', () => ({
  default: defineComponent({ name: 'TrendChart', props: ['title', 'snapshots', 'series', 'yAxisLabel', 'yMax'], template: '<div class="trend-chart-stub" />' }),
}));
vi.mock('../../../admin-shared/components/StatCard.vue', () => ({
  default: defineComponent({ name: 'StatCard', template: '<div class="stat-card-stub" />' }),
}));
vi.mock('../../../shared-ui/components/ErrorBanner.vue', () => ({
  default: defineComponent({
    name: 'ErrorBanner',
    props: ['message', 'dismissible'],
    template: '<div class="error-banner-stub" />',
  }),
}));

// ---------------------------------------------------------------------------
// vi.hoisted ensures the mockStore is created before the vi.mock factory runs
// and before any imports are processed.
// ---------------------------------------------------------------------------
const { mockStore } = vi.hoisted(() => {
  return {
    mockStore: {
      perfDetailData: null as unknown,
      perfHistoryData: [] as unknown[],
    },
  };
});

vi.mock('../../../admin-shared/composables/useAdminData', async () => {
  const { ref: vRef } = await import('vue');
  return {
    usePerfDetail: () => ({
      data: vRef(mockStore.perfDetailData),
      loading: vRef(false),
      error: vRef(''),
      refresh: async () => null,
    }),
    usePerfHistory: () => ({
      data: vRef(mockStore.perfHistoryData),
      loading: vRef(false),
      error: vRef(''),
      refresh: async () => null,
    }),
    useMetrics: () => ({
      data: vRef(null),
      loading: vRef(false),
      error: vRef(''),
      refresh: async () => null,
    }),
  };
});

// ---------------------------------------------------------------------------
// Import SFCs after mocks are hoisted
// ---------------------------------------------------------------------------
// @ts-expect-error — JS SFCs (no lang="ts") lack declaration files; informational gate only
import CacheTab from '../CacheTab.vue';
// @ts-expect-error — JS SFCs (no lang="ts") lack declaration files; informational gate only
import PerformanceTab from '../PerformanceTab.vue';

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------
const REDIS_BASE = {
  used_memory: 10_000_000,
  used_memory_human: '9.54 MB',
  peak_memory: 12_000_000,
  peak_memory_human: '11.44 MB',
  maxmemory: 0,
  maxmemory_human: '0B',
  connected_clients: 3,
  hit_rate: 0.87,
  namespaces: [{ name: 'wip', key_count: 42 }],
};

const DB_POOL_BASE = {
  status: {
    checked_out: 2,
    checked_in: 8,
    saturation: 0.2,
    overflow: 0,
    max_capacity: 10,
    slow_query_active: 0,
    slow_query_waiting: 0,
  },
  config: { pool_size: 10, pool_recycle: 3600, pool_timeout: 30 },
};

const DIRECT_CONNECTIONS_BASE = { total_since_start: 5 };

const ROUTE_CACHE_BASE = {
  mode: 'l1+l2',
  l1_size: 100,
  l1_hit_rate: 0.7,
  l2_hit_rate: 0.15,
  miss_rate: 0.15,
  reads_total: 500,
};

const PROCESS_CACHES_BASE = {
  wip_filter: { description: 'WIP filter cache', entries: 10, max_size: 100, ttl_seconds: 300 },
};

function makeFullPayload(overrides: Record<string, unknown> = {}) {
  return {
    db_pool: DB_POOL_BASE,
    direct_connections: DIRECT_CONNECTIONS_BASE,
    redis: {
      ...REDIS_BASE,
      evicted_keys: 123,
      expired_keys: 456,
      mem_fragmentation_ratio: 1.234,
      slowlog: [
        { id: 1, duration_us: 50000, command: 'HGETALL cache:wip' },
        { id: 2, duration_us: 30000, command: 'GET session:abc' },
      ],
    },
    route_cache: ROUTE_CACHE_BASE,
    process_caches: PROCESS_CACHES_BASE,
    duckdb: {
      temp_dir_bytes: 129_335_296, // ~123.4 MB
      memory_limit_state: 'limited',
    },
    ...overrides,
  };
}

// Helper: mount CacheTab with data pre-loaded in mockStore
function mountCache(payload: unknown) {
  mockStore.perfDetailData = payload;
  return mount(CacheTab, { attachTo: document.body });
}

// Helper: mount PerformanceTab with data pre-loaded in mockStore
function mountPerf(payload: unknown) {
  mockStore.perfDetailData = payload;
  return mount(PerformanceTab, { attachTo: document.body });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('PerfDetail — admin-perf-detail-ui', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    mockStore.perfDetailData = null;
    mockStore.perfHistoryData = [];
  });

  it('renders evicted_keys and expired_keys as integers', async () => {
    const wrapper = mountCache(makeFullPayload());
    await wrapper.vm.$nextTick();
    const text = wrapper.text();
    expect(text).toContain('123');
    expect(text).toContain('456');
  });

  it('renders mem_fragmentation_ratio with at most 2 decimal places', async () => {
    const wrapper = mountCache(makeFullPayload());
    await wrapper.vm.$nextTick();
    // 1.234 formatted to toFixed(2) → "1.23"
    expect(wrapper.text()).toContain('1.23');
  });

  it('renders each slowlog entry when array is non-empty', async () => {
    const wrapper = mountCache(makeFullPayload());
    await wrapper.vm.$nextTick();
    const html = wrapper.html();
    expect(html).toContain('HGETALL cache:wip');
    // duration_us: 50000 → formatDuration renders as "50.0ms"
    expect(html).toContain('50.0ms');
    expect(html).toContain('GET session:abc');
    // duration_us: 30000 → formatDuration renders as "30.0ms"
    expect(html).toContain('30.0ms');
    // Must have list items
    expect(wrapper.findAll('li').length).toBeGreaterThanOrEqual(2);
  });

  it('renders placeholder when slowlog is null', async () => {
    const wrapper = mountCache(makeFullPayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: null },
    }));
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('無慢查詢記錄');
    expect(wrapper.findAll('li').length).toBe(0);
  });

  it('renders placeholder when slowlog is empty array', async () => {
    const wrapper = mountCache(makeFullPayload({
      redis: { ...REDIS_BASE, evicted_keys: 0, expired_keys: 0, mem_fragmentation_ratio: 1.0, slowlog: [] },
    }));
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('無慢查詢記錄');
    expect(wrapper.findAll('li').length).toBe(0);
  });

  it('renders temp_dir_bytes as human-readable size', async () => {
    const wrapper = mountPerf(makeFullPayload());
    await wrapper.vm.$nextTick();
    // 129335296 bytes ≈ 123.4 MB
    const text = wrapper.text();
    expect(text).toMatch(/\d+(\.\d+)?\s*MB/);
  });

  it('renders memory_limit_state string value', async () => {
    const wrapper = mountPerf(makeFullPayload());
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('limited');
  });

  it('renders placeholder when memory_limit_state is null', async () => {
    const wrapper = mountPerf(makeFullPayload({
      duckdb: { temp_dir_bytes: 1024, memory_limit_state: null },
    }));
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toContain('N/A');
  });

  it('all new fields null: no error thrown and sibling sections still render', async () => {
    const payload = makeFullPayload({
      redis: { ...REDIS_BASE, evicted_keys: null, expired_keys: null, mem_fragmentation_ratio: null, slowlog: null },
      duckdb: null,
    });
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const cacheWrapper = mountCache(payload);
    const perfWrapper = mountPerf(payload);
    await cacheWrapper.vm.$nextTick();
    await perfWrapper.vm.$nextTick();

    expect(consoleSpy).not.toHaveBeenCalled();
    // Redis section renders (redis object is non-null, just new fields are null)
    expect(cacheWrapper.text()).toContain('Redis');
    // DuckDB section shows "未啟用" fallback when duckdb is null
    expect(perfWrapper.text()).toContain('DuckDB');
    expect(perfWrapper.text()).toContain('未啟用');
    consoleSpy.mockRestore();
  });

  it('pre-existing performance-detail fields still render with full payload', async () => {
    // CacheTab: redis section, namespaces, route cache
    const cacheWrapper = mountCache(makeFullPayload());
    await cacheWrapper.vm.$nextTick();
    expect(cacheWrapper.text()).toContain('9.54 MB');   // used_memory_human
    expect(cacheWrapper.text()).toContain('wip');        // namespace name
    expect(cacheWrapper.text()).toContain('Route Cache');

    // PerformanceTab: pool section
    const perfWrapper = mountPerf(makeFullPayload());
    await perfWrapper.vm.$nextTick();
    expect(perfWrapper.text()).toContain('連線池');
  });
});
