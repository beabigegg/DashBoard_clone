import test from 'node:test';
import assert from 'node:assert/strict';

import { useEquipmentQuery } from '../src/query-tool/composables/useEquipmentQuery.js';
import { useLotDetail } from '../src/query-tool/composables/useLotDetail.js';
import { useLotLineage } from '../src/query-tool/composables/useLotLineage.js';
import { useLotResolve } from '../src/query-tool/composables/useLotResolve.js';


function setupWindowMesApi({ get, post } = {}) {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  globalThis.window = {
    MesApi: {
      get: get || (async () => ({})),
      post: post || (async () => ({})),
    },
    setTimeout: globalThis.setTimeout.bind(globalThis),
    clearTimeout: globalThis.clearTimeout.bind(globalThis),
  };
  globalThis.document = {
    querySelector: () => null,
  };

  return () => {
    globalThis.window = originalWindow;
    globalThis.document = originalDocument;
  };
}


test('useLotResolve validates multi-query size and resolves deduplicated inputs', async () => {
  const postCalls = [];
  const restore = setupWindowMesApi({
    post: async (url, payload) => {
      postCalls.push({ url, payload });
      return {
        data: {
          data: payload.values.map((value, index) => ({
            container_id: `CID-${index + 1}`,
            input_value: value,
          })),
          not_found: [],
          expansion_info: {},
        },
      };
    },
  });

  try {
    const resolver = useLotResolve({
      inputType: 'work_order',
      allowedTypes: ['work_order', 'lot_id'],
    });

    resolver.setInputText(Array.from({ length: 51 }, (_, idx) => `WO-${idx + 1}`).join('\n'));
    const overLimit = await resolver.resolveLots();
    assert.equal(overLimit.ok, false);
    assert.equal(overLimit.reason, 'validation');
    assert.match(resolver.errorMessage.value, /50/);
    assert.equal(postCalls.length, 0);

    resolver.setInputText('WO-001\nWO-001, WO-002');
    const resolved = await resolver.resolveLots();

    assert.equal(resolved.ok, true);
    assert.equal(postCalls.length, 1);
    assert.deepEqual(postCalls[0].payload.values, ['WO-001', 'WO-002']);
    assert.equal(resolver.resolvedLots.value.length, 2);
    assert.match(resolver.successMessage.value, /解析完成/);
  } finally {
    restore();
  }
});


test('useLotLineage deduplicates in-flight lineage requests and stores graph data', async () => {
  const postCalls = [];
  const restore = setupWindowMesApi({
    post: async (url, payload) => {
      postCalls.push({ url, payload });
      await new Promise((resolve) => setTimeout(resolve, 15));
      return {
        data: {
          roots: ['CID-ROOT'],
          children_map: {
            'CID-ROOT': ['CID-CHILD'],
            'CID-CHILD': [],
          },
          names: {
            'CID-ROOT': 'LOT-ROOT',
            'CID-CHILD': 'LOT-CHILD',
          },
          nodes: {
            'CID-ROOT': { container_name: 'LOT-ROOT', container_id: 'CID-ROOT' },
            'CID-CHILD': { container_name: 'LOT-CHILD', container_id: 'CID-CHILD' },
          },
          edges: [
            {
              from_cid: 'CID-ROOT',
              to_cid: 'CID-CHILD',
              edge_type: 'split',
            },
          ],
          leaf_serials: {
            'CID-CHILD': ['SN-001'],
          },
        },
      };
    },
  });

  try {
    const lineage = useLotLineage();
    await Promise.all([
      lineage.fetchLineage(['CID-ROOT']),
      lineage.fetchLineage(['CID-ROOT']),
    ]);

    assert.equal(postCalls.length, 1);
    assert.deepEqual(postCalls[0].payload.container_ids, ['CID-ROOT']);
    assert.deepEqual(lineage.getChildren('CID-ROOT'), ['CID-CHILD']);
    assert.deepEqual(lineage.getSerials('CID-CHILD'), ['SN-001']);
    assert.equal(lineage.nameMap.get('CID-ROOT'), 'LOT-ROOT');
    assert.equal(lineage.graphEdges.value.length, 1);
  } finally {
    restore();
  }
});


test('useEquipmentQuery performs timeline multi-query and keeps validation errors user-friendly', async () => {
  const postCalls = [];
  const restore = setupWindowMesApi({
    get: async (url) => {
      if (url === '/api/query-tool/equipment-list') {
        return {
          data: {
            data: [
              { RESOURCEID: 'EQ-1', RESOURCENAME: 'EQ Alpha' },
              { RESOURCEID: 'EQ-2', RESOURCENAME: 'EQ Beta' },
            ],
          },
        };
      }
      throw new Error(`unexpected GET url: ${url}`);
    },
    post: async (url, payload) => {
      postCalls.push({ url, payload });
      if (payload.query_type === 'status_hours') {
        return { data: { data: [{ STATUSNAME: 'RUN', HOURS: 12 }] } };
      }
      if (payload.query_type === 'lots') {
        const page = Number(payload.page || 1);
        const perPage = Number(payload.per_page || 200);
        return {
          data: {
            data: [{ CONTAINERID: `CID-100${page}` }],
            pagination: { page, per_page: perPage, total: 3, total_pages: 3 },
          },
        };
      }
      if (payload.query_type === 'jobs') {
        return { data: { data: [{ JOBID: 'JOB-001' }] } };
      }
      return { data: { data: [] } };
    },
  });

  try {
    const equipment = useEquipmentQuery({
      selectedEquipmentIds: ['EQ-1'],
      startDate: '2026-02-01',
      endDate: '2026-02-10',
      activeSubTab: 'timeline',
    });

    const bootstrapped = await equipment.bootstrap();
    assert.equal(bootstrapped, true);
    assert.equal(equipment.equipmentOptions.value.length, 2);

    const queried = await equipment.queryTimeline();
    assert.equal(queried, true);
    assert.deepEqual(
      postCalls.map((call) => call.payload.query_type).sort(),
      ['jobs', 'lots', 'status_hours'],
    );
    assert.equal(equipment.queried.timeline, true);
    assert.equal(equipment.statusRows.value.length, 1);
    assert.equal(equipment.jobsRows.value.length, 1);
    assert.equal(equipment.lotsRows.value.length, 1);
    assert.equal(equipment.lotsPagination.value.total_pages, 3);

    const timelineLotsCall = postCalls.find((call) => call.payload.query_type === 'lots');
    assert.equal(timelineLotsCall.payload.page, 1);
    assert.equal(timelineLotsCall.payload.per_page, 200);

    const page2Ok = await equipment.queryLots({ page: 2 });
    assert.equal(page2Ok, true);
    const latestLotsCall = postCalls.filter((call) => call.payload.query_type === 'lots').at(-1);
    assert.equal(latestLotsCall.payload.page, 2);
    assert.equal(latestLotsCall.payload.per_page, 200);
    assert.equal(equipment.lotsPagination.value.page, 2);

    equipment.setSelectedEquipmentIds([]);
    const invalid = await equipment.queryLots();
    assert.equal(invalid, false);
    assert.match(equipment.errors.filters, /至少一台設備/);
  } finally {
    restore();
  }
});


test('useLotDetail single-item mode captures quality_meta from response and clears on complete status', async () => {
  let callCount = 0;
  const restore = setupWindowMesApi({
    get: async (url) => {
      const parsed = new URL(url, 'http://local.test');
      if (parsed.pathname === '/api/query-tool/lot-history') {
        callCount++;
        const status = callCount === 1 ? 'partial' : 'complete';
        // apiGet returns window.MesApi.get result directly;
        // composable reads payload?.data as the inner object containing data/pagination/quality_meta
        return {
          data: {
            data: [{ CONTAINERID: 'CID-001', EQUIPMENTID: 'EQ-01' }],
            pagination: { page: 1, per_page: 200, total: 1, total_pages: 1 },
            quality_meta: { status, reasons: status === 'partial' ? ['chunk_failure'] : [] },
          },
        };
      }
      if (parsed.pathname === '/api/query-tool/lot-associations') {
        return {
          data: {
            data: [],
            pagination: { page: 1, per_page: 200, total: 0, total_pages: 1 },
            quality_meta: { status: 'complete', reasons: [] },
          },
        };
      }
      return { data: {} };
    },
  });

  try {
    const detail = useLotDetail({ activeSubTab: 'history' });

    // Single-item mode: setSelectedContainerId sends container_id param
    const ok = await detail.setSelectedContainerId('CID-001');
    assert.equal(ok, true);

    // quality_meta should be captured from the non-complete single-item response
    assert.equal(detail.qualityMeta.history?.status, 'partial',
      'single-item history quality_meta should be partial');

    // Refreshing with complete status should clear the warning
    await detail.loadHistory({ force: true });
    assert.equal(detail.qualityMeta.history?.status, 'complete',
      'quality_meta should update to complete after refresh');
  } finally {
    restore();
  }
});


test('useLotDetail single-item association captures quality_meta for paged tabs', async () => {
  const restore = setupWindowMesApi({
    get: async (url) => {
      const parsed = new URL(url, 'http://local.test');
      if (parsed.pathname === '/api/query-tool/lot-history') {
        return {
          data: {
            data: [{ CONTAINERID: 'CID-001', EQUIPMENTID: 'EQ-01' }],
            pagination: { page: 1, per_page: 200, total: 1, total_pages: 1 },
            quality_meta: { status: 'complete', reasons: [] },
          },
        };
      }
      if (parsed.pathname === '/api/query-tool/lot-associations') {
        const assocType = parsed.searchParams.get('type');
        return {
          data: {
            data: [{ TYPE: assocType }],
            pagination: { page: 1, per_page: 200, total: 1, total_pages: 1 },
            quality_meta: { status: 'truncated', reasons: ['max_total_rows_exceeded'] },
          },
        };
      }
      return { data: {} };
    },
  });

  try {
    const detail = useLotDetail({ activeSubTab: 'materials' });
    await detail.setSelectedContainerId('CID-001');

    // materials is a PAGED_SUB_TAB: should capture quality_meta from single-item response
    assert.equal(detail.qualityMeta.materials?.status, 'truncated',
      'single-item materials quality_meta should be truncated');

    // Switch to holds tab and verify that tab also gets quality_meta
    await detail.setActiveSubTab('holds');
    assert.equal(detail.qualityMeta.holds?.status, 'truncated',
      'single-item holds quality_meta should be truncated');
  } finally {
    restore();
  }
});


test('useLotDetail batches selected container ids and preserves workcenter filters in follow-up query', async () => {
  const getCalls = [];
  const restore = setupWindowMesApi({
    get: async (url) => {
      getCalls.push(url);
      const parsed = new URL(url, 'http://local.test');
      if (parsed.pathname === '/api/query-tool/lot-history') {
        const page = Number(parsed.searchParams.get('page') || 1);
        const perPage = Number(parsed.searchParams.get('per_page') || 200);
        return {
          data: {
            data: page === 1
              ? [
                  {
                    CONTAINERID: 'CID-001',
                    EQUIPMENTID: 'EQ-01',
                    TRACKINTIMESTAMP: '2026-02-01 08:00:00',
                    TRACKOUTTIMESTAMP: '2026-02-01 08:30:00',
                  },
                ]
              : [
                  {
                    CONTAINERID: 'CID-002',
                    EQUIPMENTID: 'EQ-02',
                    TRACKINTIMESTAMP: '2026-02-01 09:00:00',
                    TRACKOUTTIMESTAMP: '2026-02-01 09:30:00',
                  },
                ],
            pagination: { page, per_page: perPage, total: 3, total_pages: 2 },
            quality_meta: {
              status: page === 1 ? 'truncated' : 'complete',
              reasons: page === 1 ? ['max_total_rows_exceeded'] : [],
            },
          },
        };
      }
      if (parsed.pathname === '/api/query-tool/lot-associations') {
        const assocType = parsed.searchParams.get('type');
        const page = Number(parsed.searchParams.get('page') || 1);
        const perPage = Number(parsed.searchParams.get('per_page') || 200);
        return {
          data: {
            data: [{ TYPE: assocType, CONTAINERID: 'CID-001' }],
            pagination: { page, per_page: perPage, total: 1, total_pages: 1 },
            quality_meta: {
              status: assocType === 'materials' ? 'partial' : 'complete',
              reasons: assocType === 'materials' ? ['chunk_failure'] : [],
            },
          },
        };
      }
      if (parsed.pathname === '/api/query-tool/workcenter-groups') {
        return { data: { data: [{ name: 'WB', sequence: 1 }] } };
      }
      throw new Error(`unexpected GET url: ${url}`);
    },
  });

  try {
    const detail = useLotDetail({ activeSubTab: 'history' });
    const ok = await detail.setSelectedContainerIds(['CID-001', 'CID-002']);
    assert.equal(ok, true);
    assert.equal(detail.historyRows.value.length, 1);
    assert.equal(detail.associationRows.holds.length, 1);
    assert.equal(detail.associationRows.materials.length, 1);
    assert.equal(detail.pagination.history.total_pages, 2);
    assert.equal(detail.qualityMeta.history?.status, 'truncated');
    assert.equal(detail.qualityMeta.materials?.status, 'partial');

    const historyCall = getCalls.find((url) => url.startsWith('/api/query-tool/lot-history?'));
    assert.ok(historyCall, 'lot-history API should be called');
    const historyParams = new URL(historyCall, 'http://local.test').searchParams;
    assert.equal(historyParams.get('container_ids'), 'CID-001,CID-002');
    assert.equal(historyParams.get('page'), '1');
    assert.equal(historyParams.get('per_page'), '200');

    const page2 = await detail.setSubTabPage('history', 2);
    assert.equal(page2, true);
    assert.equal(detail.pagination.history.page, 2);
    assert.equal(detail.qualityMeta.history?.status, 'complete');
    const page2Call = getCalls.filter((url) => url.startsWith('/api/query-tool/lot-history?')).at(-1);
    const page2Params = new URL(page2Call, 'http://local.test').searchParams;
    assert.equal(page2Params.get('page'), '2');
    assert.equal(page2Params.get('per_page'), '200');

    await detail.setSelectedWorkcenterGroups(['WB']);
    const latestHistoryCall = getCalls.filter((url) => url.startsWith('/api/query-tool/lot-history?')).at(-1);
    const latestParams = new URL(latestHistoryCall, 'http://local.test').searchParams;
    assert.equal(latestParams.get('workcenter_groups'), 'WB');
  } finally {
    restore();
  }
});
