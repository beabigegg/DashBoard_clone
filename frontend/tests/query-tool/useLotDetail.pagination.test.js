import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLotDetail } from '../../src/query-tool/composables/useLotDetail.js';

// lot-history / lot-associations are POSTed (container_ids batch travels in the
// body, not an over-long URL), so the mock reads params from the JSON payload.
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

describe('useLotDetail pagination', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete globalThis.window;
    delete globalThis.document;
  });

  it('resets page to 1 when per-page changes for history and materials tabs', async () => {
    const postCalls = [];
    setupWindowMesApi({
      post: async (url, payload) => {
        postCalls.push({ url, payload });

        if (url === '/api/query-tool/lot-history') {
          const page = Number(payload?.page || 1);
          const perPage = Number(payload?.per_page || 25);
          return {
            data: {
              data: [{ CONTAINERID: `CID-H-${page}`, EQUIPMENTID: 'EQ-01' }],
              pagination: { page, per_page: perPage, total: 8, total_pages: Math.max(1, Math.ceil(8 / perPage)) },
              quality_meta: { status: 'complete', reasons: [] },
            },
          };
        }

        if (url === '/api/query-tool/lot-associations') {
          const assocType = payload?.type;
          const page = Number(payload?.page || 1);
          const perPage = Number(payload?.per_page || 25);
          return {
            data: {
              data: [{ TYPE: assocType, PAGE: page }],
              pagination: { page, per_page: perPage, total: 5, total_pages: Math.max(1, Math.ceil(5 / perPage)) },
              quality_meta: { status: 'complete', reasons: [] },
            },
          };
        }

        return { data: {} };
      },
    });

    const detail = useLotDetail({ activeSubTab: 'history' });
    await detail.setSelectedContainerId('CID-001');

    await detail.setSubTabPage('history', 2);
    expect(detail.pagination.history.page).toBe(2);

    await detail.setSubTabPerPage('history', 50);
    expect(detail.pagination.history.page).toBe(1);
    expect(detail.pagination.history.per_page).toBe(50);
    const latestHistoryCall = postCalls.filter((c) => c.url === '/api/query-tool/lot-history').at(-1);
    expect(latestHistoryCall.payload.page).toBe(1);
    expect(latestHistoryCall.payload.per_page).toBe(50);

    await detail.setActiveSubTab('materials');
    await detail.setSubTabPage('materials', 3);
    expect(detail.pagination.materials.page).toBe(3);

    await detail.setSubTabPerPage('materials', 100);
    expect(detail.pagination.materials.page).toBe(1);
    expect(detail.pagination.materials.per_page).toBe(100);
    const latestMaterialsCall = postCalls
      .filter((c) => c.url === '/api/query-tool/lot-associations' && c.payload?.type === 'materials')
      .at(-1);
    expect(latestMaterialsCall.payload.page).toBe(1);
    expect(latestMaterialsCall.payload.per_page).toBe(100);
  });
});
