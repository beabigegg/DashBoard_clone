<script setup>
import { computed } from 'vue';

import { buildResourceKpiFromHours, calcYieldPct, calcOeePct } from '../../core/compute.js';
import HierarchyTable from '../../resource-shared/components/HierarchyTable.vue';

const props = defineProps({
  detailData: {
    type: Array,
    default: () => [],
  },
  expandedState: {
    type: Object,
    default: () => ({}),
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['toggle-row', 'toggle-all', 'export-csv']);

function normalizeKey(value) {
  return String(value || 'unknown').replace(/[^\w\u4e00-\u9fa5-]+/g, '_');
}

function createHourBucket() {
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

function mergeHours(target, source) {
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

function enrichWithKpi(hours) {
  return {
    ...hours,
    ...buildResourceKpiFromHours(hours),
  };
}

function buildHierarchy(data) {
  const wcMap = new Map();

  (data || []).forEach((item, index) => {
    const workcenter = item.workcenter || 'UNKNOWN';
    const family = item.family || 'UNKNOWN';
    const resourceName = item.resource || item.HISTORYID || `RESOURCE_${index + 1}`;
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

    const wcNode = wcMap.get(workcenter);

    if (!wcNode.familyMap.has(family)) {
      const familyNode = {
        id: `fam_${normalizeKey(workcenter)}_${normalizeKey(family)}`,
        level: 1,
        name: family,
        workcenter,
        family,
        metrics: createHourBucket(),
        children: [],
      };

      wcNode.familyMap.set(family, familyNode);
      wcNode.children.push(familyNode);
    }

    const familyNode = wcNode.familyMap.get(family);

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

    familyNode.children.push({
      id: `res_${normalizeKey(workcenter)}_${normalizeKey(family)}_${normalizeKey(resourceName)}_${index}`,
      level: 2,
      name: resourceName,
      metrics: resourceMetrics,
    });

    mergeHours(familyNode.metrics, resourceMetrics);
    mergeHours(wcNode.metrics, resourceMetrics);
  });

  return [...wcMap.values()]
    .map((wcNode) => {
      wcNode.metrics = enrichWithKpi(wcNode.metrics);

      wcNode.children.sort((left, right) => {
        const diff = Number(right.metrics.machine_count || 0) - Number(left.metrics.machine_count || 0);
        if (diff !== 0) {
          return diff;
        }
        return String(left.name).localeCompare(String(right.name), 'zh-Hant');
      });

      wcNode.children.forEach((familyNode) => {
        familyNode.metrics = enrichWithKpi(familyNode.metrics);
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

function formatHourPct(hours, pct) {
  return `${Number(hours || 0).toFixed(1)}h (${Number(pct || 0).toFixed(1)}%)`;
}

const hierarchy = computed(() => buildHierarchy(props.detailData));

const columns = computed(() => {
  return [
    {
      key: 'ou',
      label: 'OU%',
      value: (node) => `${Number(node.metrics?.ou_pct || 0).toFixed(1)}%`,
      className: 'col-total',
    },
    {
      key: 'oee',
      label: 'OEE%',
      value: (node) => {
        const t = Number(node.metrics?.trackout_qty || 0);
        const n = Number(node.metrics?.ng_qty || 0);
        if (t + n === 0) return '—';
        return `${Number(node.metrics?.oee_pct || 0).toFixed(1)}%`;
      },
      className: 'col-total',
    },
    {
      key: 'availability',
      label: 'AVAIL%',
      value: (node) => `${Number(node.metrics?.availability_pct || 0).toFixed(1)}%`,
      className: 'col-total',
    },
    {
      key: 'PRD',
      label: 'PRD',
      className: 'col-prd detail-cell',
      value: (node) => formatHourPct(node.metrics?.prd_hours, node.metrics?.prd_pct),
    },
    {
      key: 'SBY',
      label: 'SBY',
      className: 'col-sby detail-cell',
      value: (node) => formatHourPct(node.metrics?.sby_hours, node.metrics?.sby_pct),
    },
    {
      key: 'UDT',
      label: 'UDT',
      className: 'col-udt detail-cell',
      value: (node) => formatHourPct(node.metrics?.udt_hours, node.metrics?.udt_pct),
    },
    {
      key: 'SDT',
      label: 'SDT',
      className: 'col-sdt detail-cell',
      value: (node) => formatHourPct(node.metrics?.sdt_hours, node.metrics?.sdt_pct),
    },
    {
      key: 'EGT',
      label: 'EGT',
      className: 'col-egt detail-cell',
      value: (node) => formatHourPct(node.metrics?.egt_hours, node.metrics?.egt_pct),
    },
    {
      key: 'NST',
      label: 'NST',
      className: 'col-nst detail-cell',
      value: (node) => formatHourPct(node.metrics?.nst_hours, node.metrics?.nst_pct),
    },
    {
      key: 'count',
      label: 'Count',
      className: 'col-total',
      value: (node) => Number(node.metrics?.machine_count || 0),
    },
  ];
});

function handleToggleAll(expand) {
  const rowIds = [];
  hierarchy.value.forEach((wcNode) => {
    rowIds.push(wcNode.id);
    wcNode.children.forEach((familyNode) => {
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
          <button type="button" class="ui-btn ui-btn--sm" :disabled="loading" @click="$emit('export-csv')">匯出 CSV</button>
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
