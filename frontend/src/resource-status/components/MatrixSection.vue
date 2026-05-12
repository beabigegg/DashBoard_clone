<script setup>
import { computed } from 'vue';

import HierarchyTable from '../../resource-shared/components/HierarchyTable.vue';
import {
  MATRIX_STATUS_COLUMNS,
  STATUS_DISPLAY_MAP,
  normalizeStatus,
  resolveOuBadgeClass,
} from '../../resource-shared/constants';

const props = defineProps({
  equipment: {
    type: Array,
    default: () => [],
  },
  expandedState: {
    type: Object,
    default: () => ({}),
  },
  matrixFilter: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(['toggle-row', 'toggle-all', 'cell-filter']);

function createCounts() {
  return {
    total: 0,
    PRD: 0,
    SBY: 0,
    UDT: 0,
    SDT: 0,
    EGT: 0,
    NST: 0,
    OTHER: 0,
  };
}

function normalizeKey(value) {
  return String(value || 'unknown').replace(/[^\w\u4e00-\u9fa5-]+/g, '_');
}

function buildResourceNode(eq, groupName, familyName, statusKey, index) {
  const resourceId = eq.RESOURCEID || `resource_${index}`;
  const statusRaw = String(eq.EQUIPMENTASSETSSTATUS || '--').toUpperCase();

  return {
    id: `res_${normalizeKey(groupName)}_${normalizeKey(familyName)}_${normalizeKey(resourceId)}`,
    level: 2,
    name: eq.RESOURCENAME || eq.RESOURCEID || '--',
    workcenterGroup: groupName,
    family: familyName,
    resource: eq.RESOURCEID || null,
    statusKey,
    statusRaw,
    statusCategory: String(eq.STATUS_CATEGORY || '').toLowerCase(),
    values: {
      total: 1,
    },
    rowClickable: true,
    rowPayload: {
      workcenter_group: groupName,
      status: statusKey,
      family: familyName,
      resource: eq.RESOURCEID || null,
    },
  };
}

function calcOuPct(counts) {
  const denominator =
    Number(counts.PRD || 0) +
    Number(counts.SBY || 0) +
    Number(counts.UDT || 0) +
    Number(counts.SDT || 0) +
    Number(counts.EGT || 0);

  if (!denominator) {
    return 0;
  }
  return (Number(counts.PRD || 0) / denominator) * 100;
}

function isMatrixFilterMatch(filters, { group, status, family = null, resource = null }) {
  if (!filters || filters.length === 0) {
    return false;
  }

  return filters.some((f) => {
    return (
      f.workcenter_group === group &&
      f.status === status &&
      (f.family || null) === (family || null) &&
      (f.resource || null) === (resource || null)
    );
  });
}

function buildMatrixHierarchy(equipment) {
  const groupMap = new Map();

  equipment.forEach((eq, index) => {
    const groupName = eq.WORKCENTER_GROUP || 'UNKNOWN';
    const familyName = eq.RESOURCEFAMILYNAME || 'UNKNOWN';
    const groupSeq = Number(eq.WORKCENTER_GROUP_SEQ ?? 999);
    const statusKey = normalizeStatus(eq.EQUIPMENTASSETSSTATUS);

    if (!groupMap.has(groupName)) {
      groupMap.set(groupName, {
        id: `grp_${normalizeKey(groupName)}`,
        level: 0,
        name: groupName,
        workcenterGroup: groupName,
        sequence: groupSeq,
        counts: createCounts(),
        children: [],
        familyMap: new Map(),
      });
    }

    const groupNode = groupMap.get(groupName);

    if (!groupNode.familyMap.has(familyName)) {
      const familyNode = {
        id: `fam_${normalizeKey(groupName)}_${normalizeKey(familyName)}`,
        level: 1,
        name: familyName,
        workcenterGroup: groupName,
        family: familyName,
        counts: createCounts(),
        children: [],
      };
      groupNode.familyMap.set(familyName, familyNode);
      groupNode.children.push(familyNode);
    }

    const familyNode = groupNode.familyMap.get(familyName);
    familyNode.children.push(buildResourceNode(eq, groupName, familyName, statusKey, index));

    groupNode.counts.total += 1;
    groupNode.counts[statusKey] += 1;
    familyNode.counts.total += 1;
    familyNode.counts[statusKey] += 1;
  });

  const groups = [...groupMap.values()]
    .map((groupNode) => {
      groupNode.children.sort((left, right) => {
        const totalDiff = Number(right.counts.total || 0) - Number(left.counts.total || 0);
        if (totalDiff !== 0) {
          return totalDiff;
        }
        return String(left.name).localeCompare(String(right.name), 'zh-Hant');
      });

      groupNode.children.forEach((familyNode) => {
        familyNode.children.sort((left, right) =>
          String(left.name).localeCompare(String(right.name), 'zh-Hant')
        );

        familyNode.selectedColumns = Object.fromEntries(
          MATRIX_STATUS_COLUMNS.map((status) => [
            status,
            isMatrixFilterMatch(props.matrixFilter, {
              group: familyNode.workcenterGroup,
              family: familyNode.family,
              status,
            }),
          ])
        );

        familyNode.children.forEach((resourceNode) => {
          resourceNode.rowSelected = isMatrixFilterMatch(props.matrixFilter, {
            group: resourceNode.workcenterGroup,
            family: resourceNode.family,
            resource: resourceNode.resource,
            status: resourceNode.statusKey,
          });
        });
      });

      groupNode.selectedColumns = Object.fromEntries(
        MATRIX_STATUS_COLUMNS.map((status) => [
          status,
          isMatrixFilterMatch(props.matrixFilter, {
            group: groupNode.workcenterGroup,
            status,
          }),
        ])
      );

      delete groupNode.familyMap;
      return groupNode;
    })
    .sort((left, right) => {
      const seqDiff = Number(left.sequence || 999) - Number(right.sequence || 999);
      if (seqDiff !== 0) {
        return seqDiff;
      }
      return String(left.name).localeCompare(String(right.name), 'zh-Hant');
    });

  return groups;
}

const hierarchy = computed(() => buildMatrixHierarchy(props.equipment || []));

function resolveEquipmentStatusClass(node) {
  if (node.statusCategory) {
    return `eq-status ${node.statusCategory}`;
  }
  return `eq-status ${String(node.statusKey || 'other').toLowerCase()}`;
}

const columns = computed(() => {
  const baseColumns = [
    {
      key: 'total',
      label: '總數',
      className: 'col-total',
      value: (node) => {
        if (node.level === 2) {
          return 1;
        }
        return Number(node.counts?.total || 0);
      },
    },
  ];

  const statusColumns = MATRIX_STATUS_COLUMNS.map((status) => {
    const className = `col-${status.toLowerCase()}`;
    return {
      key: status,
      label: status,
      className,
      render: (node) => {
        if (node.level === 2) {
          const active = node.statusKey === status;
          return {
            text: active ? '●' : '-',
          };
        }
        return {
          text: Number(node.counts?.[status] || 0),
        };
      },
      cellClass: (node) => {
        if (node.level === 2) {
          return node.statusKey === status ? '' : 'zero';
        }
        return Number(node.counts?.[status] || 0) === 0 ? 'zero' : '';
      },
      isClickable: (node) => node.level < 2,
      isSelected: (node) => Boolean(node.selectedColumns?.[status]),
      payload: (node) => {
        if (node.level === 2) {
          return null;
        }
        return {
          workcenter_group: node.workcenterGroup,
          family: node.level === 1 ? node.family : null,
          resource: null,
          status,
        };
      },
    };
  });

  const ouColumn = {
    key: 'ou',
    label: 'OU%',
    render: (node) => {
      if (node.level === 2) {
        return {
          text: STATUS_DISPLAY_MAP[node.statusKey] || node.statusRaw || '--',
          badgeClass: resolveEquipmentStatusClass(node),
        };
      }

      const ouValue = calcOuPct(node.counts || {});
      return {
        text: `${ouValue.toFixed(1)}%`,
        badgeClass: `ou-badge ${resolveOuBadgeClass(ouValue)}`,
      };
    },
  };

  return [...baseColumns, ...statusColumns, ouColumn];
});

function handleCellClick({ payload }) {
  if (!payload) {
    return;
  }
  emit('cell-filter', payload);
}

function handleToggleAll(expand) {
  const rowIds = [];
  hierarchy.value.forEach((groupNode) => {
    rowIds.push(groupNode.id);
    groupNode.children.forEach((familyNode) => {
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
        <h2 class="section-title">狀態矩陣</h2>
        <div class="section-actions">
          <button type="button" class="ui-btn ui-btn--sm" @click="handleToggleAll(true)">全部展開</button>
          <button type="button" class="ui-btn ui-btn--sm" @click="handleToggleAll(false)">全部收合</button>
        </div>
      </div>

      <HierarchyTable
        :hierarchy="hierarchy"
        :columns="columns"
        :expanded-state="expandedState"
        name-column-label="工站群組 / 型號 / 設備"
        empty-text="無符合條件的矩陣資料"
        @toggle-row="$emit('toggle-row', $event)"
        @cell-click="handleCellClick"
      />
    </div>
  </section>
</template>
