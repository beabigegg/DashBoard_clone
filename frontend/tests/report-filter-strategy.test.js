import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildRejectOptionsRequestParams,
  buildViewParams,
  pruneRejectFilterSelections,
} from '../src/core/reject-history-filters.js';
import {
  buildResourceHistoryQueryParams,
  deriveResourceFamilyOptions,
  deriveResourceMachineOptions,
  pruneResourceFilterSelections,
} from '../src/core/resource-history-filters.js';

test('reject-history draft options params include full context', () => {
  const params = buildRejectOptionsRequestParams({
    startDate: '2026-02-01',
    endDate: '2026-02-07',
    workcenterGroups: ['WB'],
    packages: ['PKG-A'],
    reason: '001_A',
    includeExcludedScrap: true,
    excludeMaterialScrap: false,
    excludePbDiode: true,
  });

  assert.deepEqual(params, {
    start_date: '2026-02-01',
    end_date: '2026-02-07',
    workcenter_groups: ['WB'],
    packages: ['PKG-A'],
    reason: '001_A',
    include_excluded_scrap: true,
    exclude_material_scrap: false,
    exclude_pb_diode: true,
  });
});

test('reject-history prune removes invalid selected values', () => {
  const pruned = pruneRejectFilterSelections(
    {
      startDate: '2026-02-01',
      endDate: '2026-02-07',
      workcenterGroups: ['WB', 'FA'],
      packages: ['PKG-A', 'PKG-Z'],
      reason: '999_X',
      includeExcludedScrap: false,
      excludeMaterialScrap: true,
      excludePbDiode: true,
      paretoTop80: true,
    },
    {
      workcenterGroups: [{ name: 'WB', sequence: 1 }],
      packages: ['PKG-A'],
      reasons: ['001_A', '002_B'],
    }
  );

  assert.deepEqual(pruned.filters.workcenterGroups, ['WB']);
  assert.deepEqual(pruned.filters.packages, ['PKG-A']);
  assert.equal(pruned.filters.reason, '');
  assert.equal(pruned.removedCount, 3);
});

test('reject-history view params include multi-dimension pareto selections', () => {
  const params = buildViewParams('qid-001', {
    supplementaryFilters: {
      packages: ['PKG-A'],
      workcenterGroups: ['WB'],
      reason: '001_A',
    },
    trendDates: ['2026-02-01'],
    paretoSelections: {
      reason: ['001_A'],
      type: ['TYPE-A', 'TYPE-B'],
      workflow: ['WF-01'],
    },
    page: 2,
    perPage: 80,
    policyFilters: {
      includeExcludedScrap: true,
      excludeMaterialScrap: false,
      excludePbDiode: false,
    },
  });

  assert.deepEqual(params, {
    query_id: 'qid-001',
    packages: ['PKG-A'],
    workcenter_groups: ['WB'],
    reason: '001_A',
    trend_dates: ['2026-02-01'],
    sel_reason: ['001_A'],
    sel_type: ['TYPE-A', 'TYPE-B'],
    sel_workflow: ['WF-01'],
    page: 2,
    per_page: 80,
    include_excluded_scrap: 'true',
    exclude_material_scrap: 'false',
    exclude_pb_diode: 'false',
  });
});

test('resource-history derives families from upstream group and flags', () => {
  const resources = [
    { id: 'R1', name: 'MC-01', family: 'FAM-A', workcenterGroup: 'WB', isProduction: true, isKey: true, isMonitor: false },
    { id: 'R2', name: 'MC-02', family: 'FAM-B', workcenterGroup: 'WB', isProduction: true, isKey: false, isMonitor: true },
    { id: 'R3', name: 'MC-03', family: 'FAM-C', workcenterGroup: 'FA', isProduction: true, isKey: true, isMonitor: false },
  ];

  const families = deriveResourceFamilyOptions(resources, {
    workcenterGroups: ['WB'],
    isProduction: true,
    isKey: true,
    isMonitor: false,
  });

  assert.deepEqual(families, ['FAM-A']);
});

test('resource-history machine derivation and prune keep valid selections only', () => {
  const resources = [
    { id: 'R1', name: 'MC-01', family: 'FAM-A', workcenterGroup: 'WB', isProduction: true, isKey: false, isMonitor: false },
    { id: 'R2', name: 'MC-02', family: 'FAM-B', workcenterGroup: 'WB', isProduction: true, isKey: false, isMonitor: false },
    { id: 'R3', name: 'MC-03', family: 'FAM-C', workcenterGroup: 'FA', isProduction: true, isKey: true, isMonitor: false },
  ];

  const machineOptions = deriveResourceMachineOptions(resources, {
    workcenterGroups: ['WB'],
    families: ['FAM-B'],
    isProduction: true,
    isKey: false,
    isMonitor: false,
  });

  assert.deepEqual(machineOptions, [{ label: 'MC-02', value: 'R2' }]);

  const pruned = pruneResourceFilterSelections(
    {
      startDate: '2026-02-01',
      endDate: '2026-02-07',
      granularity: 'day',
      workcenterGroups: ['WB'],
      families: ['FAM-A', 'FAM-Z'],
      machines: ['R1', 'R9'],
      isProduction: true,
      isKey: false,
      isMonitor: false,
    },
    {
      familyOptions: ['FAM-A', 'FAM-B'],
      machineOptions: [{ label: 'MC-01', value: 'R1' }],
    }
  );

  assert.deepEqual(pruned.filters.families, ['FAM-A']);
  assert.deepEqual(pruned.filters.machines, ['R1']);
  assert.equal(pruned.removedCount, 2);
});

test('resource-history query params include selected arrays and enabled flags', () => {
  const params = buildResourceHistoryQueryParams({
    startDate: '2026-02-01',
    endDate: '2026-02-07',
    granularity: 'week',
    workcenterGroups: ['WB'],
    families: ['FAM-A'],
    machines: ['R1', 'R2'],
    isProduction: true,
    isKey: false,
    isMonitor: true,
  });

  assert.deepEqual(params, {
    start_date: '2026-02-01',
    end_date: '2026-02-07',
    granularity: 'week',
    workcenter_groups: ['WB'],
    families: ['FAM-A'],
    resource_ids: ['R1', 'R2'],
    is_production: '1',
    is_monitor: '1',
  });
});
