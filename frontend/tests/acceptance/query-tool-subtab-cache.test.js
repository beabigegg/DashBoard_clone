import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { loadCase } from './acceptance.loader.ts';

const pollJobUntilComplete = vi.fn();
vi.mock('../../src/shared-composables/useAsyncJobPolling', () => ({
  pollJobUntilComplete: (...args) => pollJobUntilComplete(...args),
}));

import { useEquipmentQuery } from '../../src/query-tool/composables/useEquipmentQuery.ts';

// Same window.MesApi boundary-fake convention as
// frontend/tests/query-tool/useEquipmentQuery.test.js -- only the network
// boundary is faked here, never useEquipmentQuery itself (the SUT, ADR 0010
// section 3 mock-of-SUT ban).
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

describe('query-tool-subtab-cache acceptance', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    pollJobUntilComplete.mockReset();
  });

  afterEach(() => {
    delete globalThis.window;
    delete globalThis.document;
  });

  it('revisit-same-filters-no-requery', async () => {
    const { input, expect: expected } = loadCase(
      'query-tool-subtab-cache',
      'revisit-same-filters-no-requery',
    );

    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    for (const tab of input.subtab_visit_sequence) {
      // input.filters_changed_between_visits === false: nothing mutates
      // selectedEquipmentIds/startDate/endDate between visits, matching the
      // acceptance case's "same filter set throughout" given.
      await query.setActiveSubTab(tab);
    }

    expect(countByType(postCalls, 'lots')).toBe(expected.oracle_query_call_count.lots);
    expect(countByType(postCalls, 'jobs')).toBe(expected.oracle_query_call_count.jobs);

    // Second entry into 生產紀錄 is the last item in the sequence — assert it
    // issued no additional request beyond the first-visit count above.
    const lotsVisits = input.subtab_visit_sequence.filter((t) => t === 'lots').length;
    expect(lotsVisits).toBeGreaterThan(1);
    expect(countByType(postCalls, 'lots')).toBe(1); // still 1 despite >1 visits
    expect(expected.second_lots_entry_issued_new_request).toBe(false);

    // rule queried-flags-source-of-truth: revisiting an already-queried tab
    // must never flip its loading indicator back on.
    expect(query.loading.lots).toBe(expected.second_lots_entry_shows_loading_indicator);
  });

  it('filter_change_invalidates_cache', async () => {
    const { input, expect: expected } = loadCase(
      'query-tool-subtab-cache',
      'filter_change_invalidates_cache',
    );

    const postCalls = [];
    setupWindowMesApi({ post: makeEquipmentPeriodHandler(postCalls) });

    const query = useEquipmentQuery({ activeSubTab: 'lots' });
    query.setSelectedEquipmentIds(['EQ-01']);

    for (const tab of input.subtab_visit_sequence) {
      await query.setActiveSubTab(tab);
    }
    expect(countByType(postCalls, 'lots')).toBe(1);
    const rowsBeforeFilterChange = query.lotsRows.value.slice();

    // input.filter_changed_before_revisit === true: mutate a real filter axis
    // (date range), matching the acceptance case's given/when.
    query.startDate.value = '2026-02-01';
    // rule queried-flags-source-of-truth
    expect(query.queried.lots).toBe(false);

    const callsBeforeRevisit = postCalls.length;
    await query.setActiveSubTab('lots');
    const callsSinceFilterChange = countByType(postCalls.slice(callsBeforeRevisit), 'lots');

    expect(callsSinceFilterChange).toBe(
      expected.oracle_query_call_count_after_filter_change.lots,
    );
    const staleRowsStillDisplayed = query.lotsRows.value.every((row, i) => row === rowsBeforeFilterChange[i])
      && query.lotsRows.value.length === rowsBeforeFilterChange.length
      && callsSinceFilterChange === 0;
    expect(staleRowsStillDisplayed).toBe(expected.stale_pre_change_rows_displayed);
  });
});
