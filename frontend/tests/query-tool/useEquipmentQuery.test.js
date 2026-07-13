import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const pollJobUntilComplete = vi.fn();
vi.mock('../../src/shared-composables/useAsyncJobPolling', () => ({
  pollJobUntilComplete: (...args) => pollJobUntilComplete(...args),
}));

import { useEquipmentQuery } from '../../src/query-tool/composables/useEquipmentQuery.ts';

// Mirrors the window.MesApi bridge convention used by sibling composable tests
// (see useLotEquipmentQuery.test.js) — apiGet/apiPost route through this
// bridge when window.MesApi is present.
function setupWindowMesApi({ get, post } = {}) {
  globalThis.window = {
    MesApi: {
      get: get || (async () => ({ data: {} })),
      post: post || (async () => ({ data: {} })),
    },
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis),
  };
  globalThis.document = {
    querySelector: () => null,
  };
}

const EQUIPMENT_PERIOD_URL = '/api/query-tool/equipment-period';

function makeEquipmentPeriodHandler(postCalls) {
  return async (url, payload) => {
    postCalls.push({ url, payload });
    if (url === EQUIPMENT_PERIOD_URL) {
      return {
        data: {
          data: [{ CONTAINERNAME: `ROW-${payload?.query_type}-${postCalls.length}` }],
          pagination: { page: 1, per_page: 200, total: 1, total_pages: 1 },
        },
      };
    }
    return { data: {} };
  };
}

function countByType(postCalls, queryType) {
  return postCalls.filter(
    (c) => c.url === EQUIPMENT_PERIOD_URL && c.payload?.query_type === queryType,
  ).length;
}

describe('useEquipmentQuery sub-tab cache', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    pollJobUntilComplete.mockReset();
  });

  afterEach(() => {
    delete globalThis.window;
    delete globalThis.document;
  });

  it('setActiveSubTab skips re-query when target sub-tab already queried under current filters', async () => {
    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    await query.setActiveSubTab('lots');
    expect(countByType(postCalls, 'lots')).toBe(1);

    // Revisit the same tab under unchanged filters — must not re-query.
    await query.setActiveSubTab('lots');
    expect(countByType(postCalls, 'lots')).toBe(1);
  });

  it('cycling lots→jobs→rejects→lots issues exactly one equipment-period call per query_type', async () => {
    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    await query.setActiveSubTab('lots');
    await query.setActiveSubTab('jobs');
    await query.setActiveSubTab('rejects');
    await query.setActiveSubTab('lots');

    expect(countByType(postCalls, 'lots')).toBe(1);
    expect(countByType(postCalls, 'jobs')).toBe(1);
    expect(countByType(postCalls, 'rejects')).toBe(1);
  });

  it('changing selectedEquipmentIds invalidates queried.lots/jobs/rejects', async () => {
    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    await query.setActiveSubTab('lots');
    await query.setActiveSubTab('jobs');
    await query.setActiveSubTab('rejects');
    expect(query.queried.lots).toBe(true);
    expect(query.queried.jobs).toBe(true);
    expect(query.queried.rejects).toBe(true);

    query.setSelectedEquipmentIds(['EQ-02']);
    expect(query.queried.lots).toBe(false);
    expect(query.queried.jobs).toBe(false);
    expect(query.queried.rejects).toBe(false);
  });

  it('changing startDate or endDate invalidates queried.lots/jobs/rejects', async () => {
    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    await query.setActiveSubTab('lots');
    await query.setActiveSubTab('jobs');
    expect(query.queried.lots).toBe(true);
    expect(query.queried.jobs).toBe(true);

    // App.vue mutates the date refs directly (no setter boundary) — the
    // sync watch() must observe this assignment immediately.
    query.startDate.value = '2026-02-01';
    expect(query.queried.lots).toBe(false);
    expect(query.queried.jobs).toBe(false);

    await query.setActiveSubTab('jobs');
    expect(query.queried.jobs).toBe(true);

    query.endDate.value = '2026-02-15';
    expect(query.queried.jobs).toBe(false);
  });

  it('entering a sub-tab after a filter change re-queries and replaces previously cached rows, never showing pre-change data', async () => {
    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    await query.setActiveSubTab('lots');
    const firstRows = query.lotsRows.value;
    expect(firstRows).toHaveLength(1);

    query.setSelectedEquipmentIds(['EQ-02']);
    await query.setActiveSubTab('lots');

    expect(countByType(postCalls, 'lots')).toBe(2);
    expect(query.lotsRows.value).not.toEqual(firstRows);
  });

  it('explicit refresh re-queries the active sub-tab even when filters and queried flag are unchanged', async () => {
    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    await query.setActiveSubTab('lots');
    expect(countByType(postCalls, 'lots')).toBe(1);

    // Explicit refresh bypasses the setActiveSubTab guard by design (AC-5).
    await query.queryActiveSubTab();
    expect(countByType(postCalls, 'lots')).toBe(2);

    await query.queryLots();
    expect(countByType(postCalls, 'lots')).toBe(3);
  });

  it('queried.lots/jobs/rejects are the sole cache-hit signal: forcing queried.<tab>=false directly causes the next setActiveSubTab to re-query', async () => {
    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    await query.setActiveSubTab('lots');
    expect(countByType(postCalls, 'lots')).toBe(1);

    query.queried.lots = false;
    await query.setActiveSubTab('lots');
    expect(countByType(postCalls, 'lots')).toBe(2);
  });
});
