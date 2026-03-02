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
        data: payload.values.map((value, index) => ({
          container_id: `CID-${index + 1}`,
          input_value: value,
        })),
        not_found: [],
        expansion_info: {},
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
          data: [
            { RESOURCEID: 'EQ-1', RESOURCENAME: 'EQ Alpha' },
            { RESOURCEID: 'EQ-2', RESOURCENAME: 'EQ Beta' },
          ],
        };
      }
      throw new Error(`unexpected GET url: ${url}`);
    },
    post: async (url, payload) => {
      postCalls.push({ url, payload });
      if (payload.query_type === 'status_hours') {
        return { data: [{ STATUSNAME: 'RUN', HOURS: 12 }] };
      }
      if (payload.query_type === 'lots') {
        return { data: [{ CONTAINERID: 'CID-1001' }] };
      }
      if (payload.query_type === 'jobs') {
        return { data: [{ JOBID: 'JOB-001' }] };
      }
      return { data: [] };
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

    equipment.setSelectedEquipmentIds([]);
    const invalid = await equipment.queryLots();
    assert.equal(invalid, false);
    assert.match(equipment.errors.filters, /至少一台設備/);
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
        return {
          data: [
            {
              CONTAINERID: 'CID-001',
              EQUIPMENTID: 'EQ-01',
              TRACKINTIMESTAMP: '2026-02-01 08:00:00',
              TRACKOUTTIMESTAMP: '2026-02-01 08:30:00',
            },
          ],
        };
      }
      if (parsed.pathname === '/api/query-tool/lot-associations') {
        const assocType = parsed.searchParams.get('type');
        return { data: [{ TYPE: assocType, CONTAINERID: 'CID-001' }] };
      }
      if (parsed.pathname === '/api/query-tool/workcenter-groups') {
        return { data: [{ name: 'WB', sequence: 1 }] };
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

    const historyCall = getCalls.find((url) => url.startsWith('/api/query-tool/lot-history?'));
    assert.ok(historyCall, 'lot-history API should be called');
    const historyParams = new URL(historyCall, 'http://local.test').searchParams;
    assert.equal(historyParams.get('container_ids'), 'CID-001,CID-002');

    await detail.setSelectedWorkcenterGroups(['WB']);
    const latestHistoryCall = getCalls.filter((url) => url.startsWith('/api/query-tool/lot-history?')).at(-1);
    const latestParams = new URL(latestHistoryCall, 'http://local.test').searchParams;
    assert.equal(latestParams.get('workcenter_groups'), 'WB');
  } finally {
    restore();
  }
});
