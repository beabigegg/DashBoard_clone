<script setup lang="ts">
import { computed } from 'vue';

import HierarchyTable from '../../resource-shared/components/HierarchyTable.vue';
import {
  MATRIX_STATUS_COLUMNS,
  STATUS_DISPLAY_MAP,
  normalizeStatus,
  resolveOuBadgeClass,
} from '../../resource-shared/constants';

interface LotItem {
  RUNCARDLOTID?: string;
  LOTTRACKINQTY_PCS?: number | null;
  LOTTRACKINTIME?: string | null;
}

interface EquipmentItem {
  RESOURCEID: string;
  RESOURCENAME: string;
  EQUIPMENTASSETSSTATUS: string;
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  RESOURCEFAMILYNAME: string;
  WORKCENTERNAME: string;
  LOCATIONNAME: string;
  LOT_COUNT: number | string;
  LOT_DETAILS: LotItem[];
  JOBORDER: string;
  JOBSTATUS: string;
  JOBMODEL: string;
  JOBSTAGE: string;
  JOBID: string;
  CREATEDATE: string;
  CREATEUSERNAME: string;
  CREATEUSER: string;
  TECHNICIANUSERNAME: string;
  TECHNICIANUSER: string;
  SYMPTOMCODE: string;
  CAUSECODE: string;
  REPAIRCODE: string;
  STATUS_CATEGORY: string;
  PACKAGEGROUPNAME?: string | null;
}

interface MatrixFilter {
  workcenter_group: string;
  status: string;
  family: string | null;
  resource: string | null;
}

interface StatusCounts {
  total: number;
  PRD: number;
  SBY: number;
  UDT: number;
  SDT: number;
  EGT: number;
  NST: number;
  OTHER: number;
  [key: string]: number;
}

interface ResourceNode {
  id: string;
  level: 2;
  name: string;
  workcenterGroup: string;
  family: string;
  resource: string | null;
  packageGroupName: string | null;
  statusKey: string;
  statusRaw: string;
  statusCategory: string;
  values: { total: number };
  rowClickable: boolean;
  rowPayload: MatrixFilter;
  rowSelected?: boolean;
}

interface FamilyNode {
  id: string;
  level: 1;
  name: string;
  workcenterGroup: string;
  family: string;
  counts: StatusCounts;
  children: ResourceNode[];
  selectedColumns?: Record<string, boolean>;
}

interface GroupNode {
  id: string;
  level: 0;
  name: string;
  workcenterGroup: string;
  sequence: number;
  counts: StatusCounts;
  children: FamilyNode[];
  familyMap?: Map<string, FamilyNode>;
  selectedColumns?: Record<string, boolean>;
}

interface MatrixColumn {
  key: string;
  label: string;
  className?: string;
  value?: (node: unknown) => unknown;
  render?: (node: unknown) => { text: unknown; badgeClass?: string };
  cellClass?: (node: unknown) => string;
  isClickable?: (node: unknown) => boolean;
  isSelected?: (node: unknown) => boolean;
  payload?: (node: unknown) => MatrixFilter | null;
}

const props = withDefaults(defineProps<{
  equipment?: EquipmentItem[];
  expandedState?: Record<string, boolean>;
  matrixFilter?: MatrixFilter[];
  activeSelection?: MatrixFilter | null;
}>(), {
  equipment: () => [],
  expandedState: () => ({}),
  matrixFilter: () => [],
  activeSelection: null,
});

const emit = defineEmits<{
  'toggle-row': [rowId: string];
  'toggle-all': [payload: { expand: boolean; rowIds: string[] }];
  'cell-filter': [filter: MatrixFilter];
}>();

function createCounts(): StatusCounts {
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

function normalizeKey(value: unknown): string {
  return String(value || 'unknown').replace(/[^\w\u4e00-\u9fa5-]+/g, '_');
}

function buildResourceNode(eq: EquipmentItem, groupName: string, familyName: string, statusKey: string, index: number): ResourceNode {
  const resourceId = eq.RESOURCEID || `resource_${index}`;
  const statusRaw = String(eq.EQUIPMENTASSETSSTATUS || '--').toUpperCase();

  return {
    id: `res_${normalizeKey(groupName)}_${normalizeKey(familyName)}_${normalizeKey(resourceId)}`,
    level: 2,
    name: eq.RESOURCENAME || eq.RESOURCEID || '--',
    workcenterGroup: groupName,
    family: familyName,
    resource: eq.RESOURCEID || null,
    packageGroupName: eq.PACKAGEGROUPNAME ?? null,
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

function calcOuPct(counts: StatusCounts): number {
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

function isMatrixFilterMatch(
  filters: MatrixFilter[],
  { group, status, family = null, resource = null }: { group: string; status: string; family?: string | null; resource?: string | null }
): boolean {
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

type GroupNodeBuilding = GroupNode & { familyMap: Map<string, FamilyNode> };

function buildMatrixHierarchy(equipment: EquipmentItem[]): GroupNode[] {
  const groupMap = new Map<string, GroupNodeBuilding>();

  equipment.forEach((eq, index) => {
    const groupName = eq.WORKCENTER_GROUP || 'UNKNOWN';
    const familyName = eq.RESOURCEFAMILYNAME || 'UNKNOWN';
    const groupSeq = Number(eq.WORKCENTER_GROUP_SEQ ?? 999);
    const statusKey = normalizeStatus(eq.EQUIPMENTASSETSSTATUS);

    if (!groupMap.has(groupName)) {
      groupMap.set(groupName, {
        id: `grp_${normalizeKey(groupName)}`,
        level: 0 as const,
        name: groupName,
        workcenterGroup: groupName,
        sequence: groupSeq,
        counts: createCounts(),
        children: [],
        familyMap: new Map<string, FamilyNode>(),
      });
    }

    const groupNode = groupMap.get(groupName)!;

    if (!groupNode.familyMap.has(familyName)) {
      const familyNode: FamilyNode = {
        id: `fam_${normalizeKey(groupName)}_${normalizeKey(familyName)}`,
        level: 1 as const,
        name: familyName,
        workcenterGroup: groupName,
        family: familyName,
        counts: createCounts(),
        children: [],
      };
      groupNode.familyMap.set(familyName, familyNode);
      groupNode.children.push(familyNode);
    }

    const familyNode = groupNode.familyMap.get(familyName)!;
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

      delete (groupNode as Partial<GroupNodeBuilding>).familyMap;
      return groupNode as GroupNode;
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

function resolveEquipmentStatusClass(node: ResourceNode): string {
  if (node.statusCategory) {
    return `eq-status ${node.statusCategory}`;
  }
  return `eq-status ${String(node.statusKey || 'other').toLowerCase()}`;
}

const columns = computed<MatrixColumn[]>(() => {
  const baseColumns: MatrixColumn[] = [
    {
      key: 'total',
      label: '總數',
      className: 'col-total',
      value: (node: unknown) => {
        // TODO: type hierarchy node union
        const n = node as ResourceNode | FamilyNode | GroupNode;
        if (n.level === 2) {
          return 1;
        }
        return Number((n as FamilyNode | GroupNode).counts?.total || 0);
      },
    },
  ];

  const statusColumns: MatrixColumn[] = MATRIX_STATUS_COLUMNS.map((status) => {
    const className = `col-${status.toLowerCase()}`;
    return {
      key: status,
      label: status,
      className,
      render: (node: unknown) => {
        // TODO: type hierarchy node union
        const n = node as ResourceNode | FamilyNode | GroupNode;
        if (n.level === 2) {
          const active = (n as ResourceNode).statusKey === status;
          return {
            text: active ? '●' : '-',
          };
        }
        return {
          text: Number((n as FamilyNode | GroupNode).counts?.[status] || 0),
        };
      },
      cellClass: (node: unknown): string => {
        // TODO: type hierarchy node union
        const n = node as ResourceNode | FamilyNode | GroupNode;
        if (n.level === 2) {
          return (n as ResourceNode).statusKey === status ? '' : 'zero';
        }
        return Number((n as FamilyNode | GroupNode).counts?.[status] || 0) === 0 ? 'zero' : '';
      },
      isClickable: (node: unknown): boolean => (node as { level: number }).level < 2,
      isSelected: (node: unknown): boolean => {
        const n = node as FamilyNode | GroupNode;
        return Boolean(n.selectedColumns?.[status]);
      },
      payload: (node: unknown): MatrixFilter | null => {
        // TODO: type hierarchy node union
        const n = node as ResourceNode | FamilyNode | GroupNode;
        if (n.level === 2) {
          return null;
        }
        return {
          workcenter_group: n.workcenterGroup,
          family: n.level === 1 ? (n as FamilyNode).family : null,
          resource: null,
          status,
        };
      },
    };
  });

  const packageColumn: MatrixColumn = {
    key: 'package',
    label: 'Package',
    className: 'col-package',
    render: (node: unknown) => {
      // TODO: type hierarchy node union
      const n = node as ResourceNode | FamilyNode | GroupNode;
      if (n.level === 2) {
        return { text: (n as ResourceNode).packageGroupName || '--' };
      }
      return { text: '--' };
    },
  };

  const ouColumn: MatrixColumn = {
    key: 'ou',
    label: 'OU%',
    render: (node: unknown) => {
      // TODO: type hierarchy node union
      const n = node as ResourceNode | FamilyNode | GroupNode;
      if (n.level === 2) {
        const rn = n as ResourceNode;
        return {
          text: STATUS_DISPLAY_MAP[rn.statusKey] || rn.statusRaw || '--',
          badgeClass: resolveEquipmentStatusClass(rn),
        };
      }

      const ouValue = calcOuPct((n as FamilyNode | GroupNode).counts);
      return {
        text: `${ouValue.toFixed(1)}%`,
        badgeClass: `ou-badge ${resolveOuBadgeClass(ouValue)}`,
      };
    },
  };

  return [...baseColumns, ...statusColumns, ouColumn, packageColumn];
});

function handleCellClick({ payload }: { payload: MatrixFilter | null }): void {
  if (!payload) {
    return;
  }
  emit('cell-filter', payload);
}

function handleToggleAll(expand: boolean): void {
  const rowIds: string[] = [];
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
