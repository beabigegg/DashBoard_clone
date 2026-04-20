import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useLotDetail } from '../../src/query-tool/composables/useLotDetail.js';

function setupWindowMesApi(getImpl) {
  globalThis.window = {
    MesApi: {
      get: getImpl,
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
    const getCalls = [];
    setupWindowMesApi(async (url) => {
      getCalls.push(url);
      const parsed = new URL(url, 'http://local.test');

      if (parsed.pathname === '/api/query-tool/lot-history') {
        const page = Number(parsed.searchParams.get('page') || 1);
        const perPage = Number(parsed.searchParams.get('per_page') || 25);
        return {
          data: {
            data: [{ CONTAINERID: `CID-H-${page}`, EQUIPMENTID: 'EQ-01' }],
            pagination: { page, per_page: perPage, total: 8, total_pages: Math.max(1, Math.ceil(8 / perPage)) },
            quality_meta: { status: 'complete', reasons: [] },
          },
        };
      }

      if (parsed.pathname === '/api/query-tool/lot-associations') {
        const assocType = parsed.searchParams.get('type');
        const page = Number(parsed.searchParams.get('page') || 1);
        const perPage = Number(parsed.searchParams.get('per_page') || 25);
        return {
          data: {
            data: [{ TYPE: assocType, PAGE: page }],
            pagination: { page, per_page: perPage, total: 5, total_pages: Math.max(1, Math.ceil(5 / perPage)) },
            quality_meta: { status: 'complete', reasons: [] },
          },
        };
      }

      return { data: {} };
    });

    const detail = useLotDetail({ activeSubTab: 'history' });
    await detail.setSelectedContainerId('CID-001');

    await detail.setSubTabPage('history', 2);
    expect(detail.pagination.history.page).toBe(2);

    await detail.setSubTabPerPage('history', 50);
    expect(detail.pagination.history.page).toBe(1);
    expect(detail.pagination.history.per_page).toBe(50);
    const latestHistoryCall = getCalls.filter((url) => url.startsWith('/api/query-tool/lot-history?')).at(-1);
    const historyParams = new URL(latestHistoryCall, 'http://local.test').searchParams;
    expect(historyParams.get('page')).toBe('1');
    expect(historyParams.get('per_page')).toBe('50');

    await detail.setActiveSubTab('materials');
    await detail.setSubTabPage('materials', 3);
    expect(detail.pagination.materials.page).toBe(3);

    await detail.setSubTabPerPage('materials', 100);
    expect(detail.pagination.materials.page).toBe(1);
    expect(detail.pagination.materials.per_page).toBe(100);
    const latestMaterialsCall = getCalls
      .filter((url) => url.includes('/api/query-tool/lot-associations?') && url.includes('type=materials'))
      .at(-1);
    const materialParams = new URL(latestMaterialsCall, 'http://local.test').searchParams;
    expect(materialParams.get('page')).toBe('1');
    expect(materialParams.get('per_page')).toBe('100');
  });
});
