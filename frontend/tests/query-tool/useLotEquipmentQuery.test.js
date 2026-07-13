import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const pollJobUntilComplete = vi.fn();
vi.mock('../../src/shared-composables/useAsyncJobPolling', () => ({
  pollJobUntilComplete: (...args) => pollJobUntilComplete(...args),
}));

import { useLotEquipmentQuery } from '../../src/query-tool/composables/useLotEquipmentQuery.ts';

// Mirrors the window.MesApi bridge convention used by sibling composable tests
// (see useLotDetail.pagination.test.js) — apiGet/apiPost route through this
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

const LOOKUP_URL = '/api/query-tool/lot-equipment-lookup';
const EQUIPMENT_PERIOD_URL = '/api/query-tool/equipment-period';

function makeLookupResponse(overrides = {}) {
  return {
    data: {
      equipment_ids: ['EQ-01'],
      equipment_names: ['Machine-A'],
      lot_names: ['GA25081329-A01'],
      trace_map: {},
      date_range: { start: '2026-01-01', end: '2026-01-07' },
      ...overrides,
    },
  };
}

describe('useLotEquipmentQuery', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    pollJobUntilComplete.mockReset();
  });

  afterEach(() => {
    delete globalThis.window;
    delete globalThis.document;
  });

  it('queryLots includes rows whose CONTAINERNAME has trailing whitespace/case differences after trim+uppercase (regression: CHAR-padded Oracle output)', async () => {
    const postCalls = [];
    setupWindowMesApi({
      post: async (url, payload) => {
        postCalls.push({ url, payload });

        if (url === LOOKUP_URL) {
          return makeLookupResponse();
        }

        if (url === EQUIPMENT_PERIOD_URL) {
          return {
            data: {
              data: [
                // Oracle CHAR-padded value with trailing whitespace and mixed case.
                { CONTAINERNAME: 'ga25081329-a01   ', EQUIPMENTID: 'EQ-01' },
                // Unrelated lot must still be filtered out.
                { CONTAINERNAME: 'OTHER-LOT-01', EQUIPMENTID: 'EQ-01' },
              ],
            },
          };
        }

        return { data: {} };
      },
    });

    const query = useLotEquipmentQuery({ activeSubTab: 'lots' });
    query.inputType.value = 'lot_id';
    query.inputText.value = 'GA25081329-A01';
    query.selectedWorkcenterGroups.value = ['GROUP-A'];

    const ok = await query.lookupEquipment();
    expect(ok).toBe(true);

    // queryLots() ran automatically as part of lookupEquipment()'s auto-query.
    expect(query.lotsRows.value).toHaveLength(1);
    expect(query.lotsRows.value[0].CONTAINERNAME).toBe('ga25081329-a01   ');
  });

  it('queryRejects includes rows whose CONTAINERNAME has trailing whitespace/case differences after trim+uppercase', async () => {
    setupWindowMesApi({
      post: async (url) => {
        if (url === LOOKUP_URL) {
          return makeLookupResponse();
        }

        if (url === EQUIPMENT_PERIOD_URL) {
          return {
            data: {
              data: [
                { CONTAINERNAME: 'ga25081329-a01   ', EQUIPMENTID: 'EQ-01' },
                { CONTAINERNAME: 'OTHER-LOT-01', EQUIPMENTID: 'EQ-01' },
              ],
            },
          };
        }

        return { data: {} };
      },
    });

    const query = useLotEquipmentQuery({ activeSubTab: 'rejects' });
    query.inputType.value = 'lot_id';
    query.inputText.value = 'GA25081329-A01';
    query.selectedWorkcenterGroups.value = ['GROUP-A'];

    const ok = await query.lookupEquipment();
    expect(ok).toBe(true);

    expect(query.rejectsRows.value).toHaveLength(1);
    expect(query.rejectsRows.value[0].CONTAINERNAME).toBe('ga25081329-a01   ');
  });

  it('sends container_names on the lots equipment-period payload but not on jobs/rejects payloads', async () => {
    const postCalls = [];
    setupWindowMesApi({
      post: async (url, payload) => {
        postCalls.push({ url, payload });

        if (url === LOOKUP_URL) {
          return makeLookupResponse();
        }

        if (url === EQUIPMENT_PERIOD_URL) {
          return { data: { data: [] } };
        }

        return { data: {} };
      },
    });

    const query = useLotEquipmentQuery({ activeSubTab: 'lots' });
    query.inputType.value = 'lot_id';
    query.inputText.value = 'GA25081329-A01';
    query.selectedWorkcenterGroups.value = ['GROUP-A'];

    await query.lookupEquipment();

    await query.queryJobs();
    await query.queryRejects();

    const lotsCall = postCalls.find(
      (c) => c.url === EQUIPMENT_PERIOD_URL && c.payload?.query_type === 'lots',
    );
    const jobsCall = postCalls.find(
      (c) => c.url === EQUIPMENT_PERIOD_URL && c.payload?.query_type === 'jobs',
    );
    const rejectsCall = postCalls.find(
      (c) => c.url === EQUIPMENT_PERIOD_URL && c.payload?.query_type === 'rejects',
    );

    expect(lotsCall).toBeTruthy();
    // resolvedLotNames is not part of the composable's public return surface,
    // so assert against the already-uppercased lot_names the lookup response
    // resolved (per the composable's `.map((n) => String(n).toUpperCase())`).
    expect(lotsCall.payload.container_names).toEqual(['GA25081329-A01']);

    expect(jobsCall).toBeTruthy();
    expect(jobsCall.payload).not.toHaveProperty('container_names');

    expect(rejectsCall).toBeTruthy();
    expect(rejectsCall.payload).not.toHaveProperty('container_names');
  });

  it('queryLots polls the async job envelope and populates rows from the polled result (regression: wide date-range 202 async response)', async () => {
    pollJobUntilComplete.mockResolvedValue({ status: 'finished' });

    const getCalls = [];
    setupWindowMesApi({
      get: async (url) => {
        getCalls.push(url);

        if (url === '/api/job/xxx/result') {
          return {
            data: {
              data: [
                { CONTAINERNAME: 'ga25081329-a01   ', EQUIPMENTID: 'EQ-01' },
                { CONTAINERNAME: 'OTHER-LOT-01', EQUIPMENTID: 'EQ-01' },
              ],
            },
          };
        }

        return { data: {} };
      },
      post: async (url) => {
        if (url === LOOKUP_URL) {
          return makeLookupResponse();
        }

        if (url === EQUIPMENT_PERIOD_URL) {
          return {
            data: {
              async: true,
              job_id: 'job-123',
              status_url: '/api/job/xxx',
              result_url: '/api/job/xxx/result',
            },
          };
        }

        return { data: {} };
      },
    });

    const query = useLotEquipmentQuery({ activeSubTab: 'lots' });
    query.inputType.value = 'lot_id';
    query.inputText.value = 'GA25081329-A01';
    query.selectedWorkcenterGroups.value = ['GROUP-A'];

    const ok = await query.lookupEquipment();
    expect(ok).toBe(true);

    expect(pollJobUntilComplete).toHaveBeenCalledWith('/api/job/xxx');
    expect(getCalls).toContain('/api/job/xxx/result');

    // queryLots() ran automatically as part of lookupEquipment()'s auto-query,
    // and must not end up empty just because the backend returned a 202 envelope.
    expect(query.lotsRows.value).toHaveLength(1);
    expect(query.lotsRows.value[0].CONTAINERNAME).toBe('ga25081329-a01   ');
  });

  function makeCountingEquipmentPeriodHandler(postCalls) {
    return async (url, payload) => {
      postCalls.push({ url, payload });

      if (url === LOOKUP_URL) {
        return makeLookupResponse();
      }

      if (url === EQUIPMENT_PERIOD_URL) {
        const type = payload?.query_type;
        const seq = postCalls.filter(
          (c) => c.url === EQUIPMENT_PERIOD_URL && c.payload?.query_type === type,
        ).length;
        // CONTAINERNAME/CONTAINERNAMES must exactly match (lots/rejects) or
        // substring-match (jobs) the resolved lot name from makeLookupResponse()
        // so the composable's own row filtering doesn't drop the row; SEQ is
        // the differentiator proving "replaces previously cached rows".
        return {
          data: {
            data: [{
              CONTAINERNAME: 'GA25081329-A01',
              CONTAINERNAMES: 'GA25081329-A01',
              EQUIPMENTID: 'EQ-01',
              SEQ: seq,
            }],
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

  async function setupLookedUpQuery(postCalls, { activeSubTab = 'lots' } = {}) {
    setupWindowMesApi({ post: makeCountingEquipmentPeriodHandler(postCalls) });
    const query = useLotEquipmentQuery({ activeSubTab });
    query.inputType.value = 'lot_id';
    query.inputText.value = 'GA25081329-A01';
    query.selectedWorkcenterGroups.value = ['GROUP-A'];
    await query.lookupEquipment();
    return query;
  }

  it('setActiveSubTab reuses cached lots rows without a new equipment-period POST on same-filter revisit', async () => {
    const postCalls = [];
    const query = await setupLookedUpQuery(postCalls, { activeSubTab: 'lots' });

    // lookupEquipment() auto-queried 'lots' already.
    expect(countByType(postCalls, 'lots')).toBe(1);

    await query.setActiveSubTab('lots');
    expect(countByType(postCalls, 'lots')).toBe(1);
  });

  it('cycling lots→jobs→rejects→lots issues exactly one equipment-period call per query_type', async () => {
    const postCalls = [];
    const query = await setupLookedUpQuery(postCalls, { activeSubTab: 'lots' });

    await query.setActiveSubTab('jobs');
    await query.setActiveSubTab('rejects');
    await query.setActiveSubTab('lots');

    expect(countByType(postCalls, 'lots')).toBe(1);
    expect(countByType(postCalls, 'jobs')).toBe(1);
    expect(countByType(postCalls, 'rejects')).toBe(1);
  });

  it('re-running lookupEquipment with a changed input/workcenter-group set resets queried.* before auto-query', async () => {
    const postCalls = [];
    const query = await setupLookedUpQuery(postCalls, { activeSubTab: 'lots' });

    await query.setActiveSubTab('jobs');
    await query.setActiveSubTab('rejects');
    await query.setActiveSubTab('lots');
    expect(query.queried.lots).toBe(true);
    expect(query.queried.jobs).toBe(true);
    expect(query.queried.rejects).toBe(true);

    query.inputText.value = 'GA25081329-A02';
    query.selectedWorkcenterGroups.value = ['GROUP-B'];
    await query.lookupEquipment();

    // Auto-query re-populates only the active tab ('lots'); jobs/rejects
    // must come back false, never a stale-true carried over from before.
    expect(query.queried.lots).toBe(true);
    expect(query.queried.jobs).toBe(false);
    expect(query.queried.rejects).toBe(false);
  });

  it('entering a sub-tab after re-lookup re-queries and replaces previously cached rows', async () => {
    const postCalls = [];
    const query = await setupLookedUpQuery(postCalls, { activeSubTab: 'jobs' });
    const firstJobsRows = query.jobsRows.value;
    expect(firstJobsRows).toHaveLength(1);

    query.inputText.value = 'GA25081329-A02';
    query.selectedWorkcenterGroups.value = ['GROUP-B'];
    await query.lookupEquipment();

    await query.setActiveSubTab('jobs');

    expect(countByType(postCalls, 'jobs')).toBe(2);
    expect(query.jobsRows.value).not.toEqual(firstJobsRows);
  });

  it('explicit refresh re-queries the active sub-tab even when filters and queried flag are unchanged', async () => {
    const postCalls = [];
    const query = await setupLookedUpQuery(postCalls, { activeSubTab: 'lots' });

    expect(countByType(postCalls, 'lots')).toBe(1);

    // Explicit refresh bypasses the setActiveSubTab guard by design (AC-5).
    await query.queryActiveSubTab();
    expect(countByType(postCalls, 'lots')).toBe(2);

    await query.queryLots();
    expect(countByType(postCalls, 'lots')).toBe(3);
  });

  it('queried.lots/jobs/rejects are the sole cache-hit signal: forcing queried.<tab>=false directly causes the next setActiveSubTab to re-query', async () => {
    const postCalls = [];
    const query = await setupLookedUpQuery(postCalls, { activeSubTab: 'lots' });

    expect(countByType(postCalls, 'lots')).toBe(1);

    query.queried.lots = false;
    await query.setActiveSubTab('lots');
    expect(countByType(postCalls, 'lots')).toBe(2);
  });
});
