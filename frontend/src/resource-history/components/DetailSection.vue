<script setup lang="ts">
import { computed } from 'vue';

import { buildResourceKpiFromHours, calcYieldPct, calcOeePct } from '../../core/compute';
import HierarchyTable from '../../resource-shared/components/HierarchyTable.vue';

const props = withDefaults(defineProps<{
  detailData?: unknown[];
  expandedState?: Record<string, boolean>;
  loading?: boolean;
}>(), {
  detailData: () => [],
  expandedState: () => ({}),
  loading: false,
});

const emit = defineEmits<{
  'toggle-row': [rowId: string];
  'toggle-all': [payload: { expand: boolean; rowIds: string[] }];
  'export-csv': [];
}>();

interface HourBucket {
  prd_hours: number;
  sby_hours: number;
  udt_hours: number;
  sdt_hours: number;
  egt_hours: number;
  nst_hours: number;
  trackout_qty: number;
  ng_qty: number;
  machine_count: number;
  [key: string]: unknown;
}

interface HierarchyNode {
  id: string;
  level: number;
  name: string;
  metrics: Record<string, unknown>;
  children?: HierarchyNode[];
  workcenter?: string;
  family?: string;
  sequence?: number;
  familyMap?: Map<string, HierarchyNode>;
}

function normalizeKey(value: unknown): string {
  return String(value || 'unknown').replace(/[^\w\u4e00-\u9fa5-]+/g, '_');
}

function createHourBucket(): HourBucket {
  return {
    prd_hours: 0,
    sby_hours: 0,
    udt_hours: 0,
    sdt_hours: 0,
    egt_hours: 0,
    nst_hours: 0,
    trackout_qty: 0,
    ng_qty: 0,
    machine_count: 0,
  };
}

function mergeHours(target: HourBucket, source: Record<string, unknown>): void {
  target.prd_hours += Number(source.prd_hours || 0);
  target.sby_hours += Number(source.sby_hours || 0);
  target.udt_hours += Number(source.udt_hours || 0);
  target.sdt_hours += Number(source.sdt_hours || 0);
  target.egt_hours += Number(source.egt_hours || 0);
  target.nst_hours += Number(source.nst_hours || 0);
  target.trackout_qty += Number(source.trackout_qty || 0);
  target.ng_qty += Number(source.ng_qty || 0);
  target.machine_count += Number(source.machine_count || 1);
}

function enrichWithKpi(hours: HourBucket): Record<string, unknown> {
  return {
    ...hours,
    ...buildResourceKpiFromHours(hours),
  };
}

function buildHierarchy(data: unknown[]): HierarchyNode[] {
  const wcMap = new Map<string, HierarchyNode>();

  (data || []).forEach((rawItem, index) => {
    const item = rawItem as Record<string, unknown>;
    const workcenter = String(item.workcenter || 'UNKNOWN');
    const family = String(item.family || 'UNKNOWN');
    const resourceName = String(item.resource || item.HISTORYID || `RESOURCE_${index + 1}`);
    const sequence = Number(item.workcenter_seq ?? 999);

    if (!wcMap.has(workcenter)) {
      wcMap.set(workcenter, {
        id: `wc_${normalizeKey(workcenter)}`,
        level: 0,
        name: workcenter,
        workcenter,
        sequence,
        metrics: createHourBucket(),
        children: [],
        familyMap: new Map(),
      });
    }

    const wcNode = wcMap.get(workcenter)!;

    if (!wcNode.familyMap!.has(family)) {
      const familyNode: HierarchyNode = {
        id: `fam_${normalizeKey(workcenter)}_${normalizeKey(family)}`,
        level: 1,
        name: family,
        workcenter,
        family,
        metrics: createHourBucket(),
        children: [],
      };

      wcNode.familyMap!.set(family, familyNode);
      wcNode.children!.push(familyNode);
    }

    const familyNode = wcNode.familyMap!.get(family)!;

    const resourceMetrics = enrichWithKpi({
      prd_hours: Number(item.prd_hours || 0),
      sby_hours: Number(item.sby_hours || 0),
      udt_hours: Number(item.udt_hours || 0),
      sdt_hours: Number(item.sdt_hours || 0),
      egt_hours: Number(item.egt_hours || 0),
      nst_hours: Number(item.nst_hours || 0),
      trackout_qty: Number(item.trackout_qty || 0),
      ng_qty: Number(item.ng_qty || 0),
      machine_count: Number(item.machine_count || 1),
    });

    familyNode.children!.push({
      id: `res_${normalizeKey(workcenter)}_${normalizeKey(family)}_${normalizeKey(resourceName)}_${index}`,
      level: 2,
      name: resourceName,
      metrics: resourceMetrics,
    });

    mergeHours(familyNode.metrics as HourBucket, resourceMetrics);
    mergeHours(wcNode.metrics as HourBucket, resourceMetrics);
  });

  return [...wcMap.values()]
    .map((wcNode) => {
      wcNode.metrics = enrichWithKpi(wcNode.metrics as HourBucket);

      wcNode.children!.sort((left, right) => {
        const diff = Number(right.metrics.machine_count || 0) - Number(left.metrics.machine_count || 0);
        if (diff !== 0) {
          return diff;
        }
        return String(left.name).localeCompare(String(right.name), 'zh-Hant');
      });

      wcNode.children!.forEach((familyNode) => {
        familyNode.metrics = enrichWithKpi(familyNode.metrics as HourBucket);
      });

      delete wcNode.familyMap;
      return wcNode;
    })
    .sort((left, right) => {
      const seqDiff = Number(left.sequence || 999) - Number(right.sequence || 999);
      if (seqDiff !== 0) {
        return seqDiff;
      }
      return String(left.name).localeCompare(String(right.name), 'zh-Hant');
    });
}

function formatHourPct(hours: unknown, pct: unknown): string {
  return `${Number(hours || 0).toFixed(1)}h (${Number(pct || 0).toFixed(1)}%)`;
}

const hierarchy = computed(() => buildHierarchy(props.detailData));

const columns = computed(() => {
  return [
    {
      key: 'ou',
      label: 'OU%',
      // TODO: type hierarchy node union
      value: (node: unknown) => `${Number((node as HierarchyNode).metrics?.ou_pct || 0).toFixed(1)}%`,
      className: 'col-total',
    },
    {
      key: 'oee',
      label: 'OEE%',
      // TODO: type hierarchy node union
      value: (node: unknown) => {
        const n = node as HierarchyNode;
        const t = Number(n.metrics?.trackout_qty || 0);
        const ng = Number(n.metrics?.ng_qty || 0);
        if (t + ng === 0) return '—';
        return `${Number(n.metrics?.oee_pct || 0).toFixed(1)}%`;
      },
      className: 'col-total',
    },
    {
      key: 'availability',
      label: 'AVAIL%',
      // TODO: type hierarchy node union
      value: (node: unknown) => `${Number((node as HierarchyNode).metrics?.availability_pct || 0).toFixed(1)}%`,
      className: 'col-total',
    },
    {
      key: 'PRD',
      label: 'PRD',
      className: 'col-prd detail-cell',
      // TODO: type hierarchy node union
      value: (node: unknown) => { const n = node as HierarchyNode; return formatHourPct(n.metrics?.prd_hours, n.metrics?.prd_pct); },
    },
    {
      key: 'SBY',
      label: 'SBY',
      className: 'col-sby detail-cell',
      // TODO: type hierarchy node union
      value: (node: unknown) => { const n = node as HierarchyNode; return formatHourPct(n.metrics?.sby_hours, n.metrics?.sby_pct); },
    },
    {
      key: 'UDT',
      label: 'UDT',
      className: 'col-udt detail-cell',
      // TODO: type hierarchy node union
      value: (node: unknown) => { const n = node as HierarchyNode; return formatHourPct(n.metrics?.udt_hours, n.metrics?.udt_pct); },
    },
    {
      key: 'SDT',
      label: 'SDT',
      className: 'col-sdt detail-cell',
      // TODO: type hierarchy node union
      value: (node: unknown) => { const n = node as HierarchyNode; return formatHourPct(n.metrics?.sdt_hours, n.metrics?.sdt_pct); },
    },
    {
      key: 'EGT',
      label: 'EGT',
      className: 'col-egt detail-cell',
      // TODO: type hierarchy node union
      value: (node: unknown) => { const n = node as HierarchyNode; return formatHourPct(n.metrics?.egt_hours, n.metrics?.egt_pct); },
    },
    {
      key: 'NST',
      label: 'NST',
      className: 'col-nst detail-cell',
      // TODO: type hierarchy node union
      value: (node: unknown) => { const n = node as HierarchyNode; return formatHourPct(n.metrics?.nst_hours, n.metrics?.nst_pct); },
    },
    {
      key: 'count',
      label: 'Count',
      className: 'col-total',
      // TODO: type hierarchy node union
      value: (node: unknown) => Number((node as HierarchyNode).metrics?.machine_count || 0),
    },
  ];
});

function handleToggleAll(expand: boolean): void {
  const rowIds: string[] = [];
  hierarchy.value.forEach((wcNode) => {
    rowIds.push(wcNode.id);
    wcNode.children!.forEach((familyNode) => {
      rowIds.push(familyNode.id);
    });
  });

  emit('toggle-all', { expand, rowIds });
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="section-header">
        <h2 class="section-title">明細資料</h2>
        <div class="detail-toolbar">
          <button type="button" class="ui-btn ui-btn--sm" :disabled="loading" @click="handleToggleAll(true)">全部展開</button>
          <button type="button" class="ui-btn ui-btn--sm" :disabled="loading" @click="handleToggleAll(false)">全部收合</button>
          <button type="button" class="ui-btn ui-btn--secondary" :disabled="loading" @click="$emit('export-csv')">匯出 CSV</button>
        </div>
      </div>

      <HierarchyTable
        :hierarchy="hierarchy"
        :columns="columns"
        :expanded-state="expandedState"
        name-column-label="工站 / 型號 / 設備"
        empty-text="No data"
        @toggle-row="$emit('toggle-row', $event)"
      />
    </div>
  </section>
</template>
