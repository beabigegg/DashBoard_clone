<script setup lang="ts">
import { computed } from 'vue';

interface ColumnDef {
  key: string;
  label: string;
  headerClass?: string;
  className?: string;
  cellClass?: string | ((node: unknown, display: CellDisplay) => string);
  clickable?: boolean;
  isClickable?: (node: unknown) => boolean;
  isSelected?: (node: unknown) => boolean;
  payload?: (node: unknown) => unknown;
  value?: (node: unknown) => unknown;
  render?: (node: unknown) => unknown;
}

interface CellDisplay {
  text: unknown;
  badgeClass: string;
}

const props = defineProps<{
  hierarchy?: unknown[];
  columns?: ColumnDef[];
  expandedState?: Record<string, boolean>;
  nameColumnLabel?: string;
  emptyText?: string;
  showToolbar?: boolean;
}>();

const emit = defineEmits(['cell-click', 'toggle-row', 'toggle-all']);

const resolvedColumns = computed<ColumnDef[]>(() => props.columns ?? []);
const resolvedHierarchy = computed<unknown[]>(() => props.hierarchy ?? []);
const resolvedExpandedState = computed<Record<string, boolean>>(() => props.expandedState ?? {});
const resolvedNameColumnLabel = computed<string>(() => props.nameColumnLabel ?? '名稱');
const resolvedEmptyText = computed<string>(() => props.emptyText ?? '無資料');

const hasRows = computed(
  () => Array.isArray(props.hierarchy) && props.hierarchy.length > 0
);

function getNodeChildren(node: unknown): unknown[] {
  if (!node || typeof node !== 'object') {
    return [];
  }
  const n = node as Record<string, unknown>;
  if (Array.isArray(n.children)) {
    return n.children;
  }
  if (Array.isArray(n.families)) {
    return n.families;
  }
  if (Array.isArray(n.resources)) {
    return n.resources;
  }
  if (Array.isArray(n.equipment)) {
    return n.equipment;
  }
  return [];
}

function getNodeId(
  node: unknown,
  parentId: string | null,
  index: number,
  level: number
): string {
  const n = node as Record<string, unknown> | null | undefined;
  if (n?.id) {
    return String(n.id);
  }
  if (n?.rowId) {
    return String(n.rowId);
  }
  return `${parentId || 'row'}_${level}_${index}`;
}

function hasChildren(node: unknown): boolean {
  return getNodeChildren(node).length > 0;
}

function isExpanded(node: unknown, rowId: string): boolean {
  if (!hasChildren(node)) {
    return false;
  }
  return Boolean(resolvedExpandedState.value?.[rowId]);
}

function getNodeLabel(node: unknown): string {
  const n = node as Record<string, unknown> | null | undefined;
  return String(n?.name ?? n?.label ?? '--');
}

function getIndentClass(level: number): string {
  if (level === 1) {
    return 'indent-1';
  }
  if (level === 2) {
    return 'indent-2';
  }
  return '';
}

function getRowClasses(node: unknown, level: number): string[] {
  const n = node as Record<string, unknown> | null | undefined;
  const classes = [`row-level-${level}`];
  const indentClass = getIndentClass(level);
  if (indentClass) {
    classes.push(indentClass);
  }
  if (n?.rowClass) {
    classes.push(String(n.rowClass));
  }
  if (n?.rowClickable) {
    classes.push('clickable-row');
  }
  if (n?.rowSelected) {
    classes.push('selected');
  }
  return classes;
}

function resolveCellValue(node: unknown, column: ColumnDef): unknown {
  const n = node as Record<string, unknown> | null | undefined;
  if (typeof column?.value === 'function') {
    return column.value(node);
  }
  if (
    n?.values &&
    typeof n.values === 'object' &&
    Object.prototype.hasOwnProperty.call(n.values, column.key)
  ) {
    return (n.values as Record<string, unknown>)[column.key];
  }
  if (Object.prototype.hasOwnProperty.call(n || {}, column.key)) {
    return (n as Record<string, unknown>)[column.key];
  }
  return '';
}

function getCellDisplay(node: unknown, column: ColumnDef): CellDisplay {
  const rendered =
    typeof column?.render === 'function' ? column.render(node) : resolveCellValue(node, column);
  if (rendered && typeof rendered === 'object' && !Array.isArray(rendered)) {
    const r = rendered as Record<string, unknown>;
    return {
      text: r.text ?? r.value ?? '',
      badgeClass: String(r.badgeClass || ''),
    };
  }
  return {
    text: rendered ?? '',
    badgeClass: '',
  };
}

function isCellClickable(node: unknown, column: ColumnDef): boolean {
  if (typeof column?.isClickable === 'function') {
    return Boolean(column.isClickable(node));
  }
  return Boolean(column?.clickable);
}

function isCellSelected(node: unknown, column: ColumnDef): boolean {
  const n = node as Record<string, unknown> | null | undefined;
  if (typeof column?.isSelected === 'function') {
    return Boolean(column.isSelected(node));
  }
  return Boolean(
    n?.selectedColumns &&
      typeof n.selectedColumns === 'object' &&
      (n.selectedColumns as Record<string, unknown>)[column?.key]
  );
}

function getCellClasses(node: unknown, column: ColumnDef, display: CellDisplay): string[] {
  const classes: string[] = [];
  if (column?.className) {
    classes.push(column.className);
  }
  if (typeof column?.cellClass === 'function') {
    const dynamicClass = column.cellClass(node, display);
    if (dynamicClass) {
      classes.push(dynamicClass);
    }
  } else if (column?.cellClass) {
    classes.push(column.cellClass);
  }
  if (isCellClickable(node, column)) {
    classes.push('clickable');
  }
  if (isCellSelected(node, column)) {
    classes.push('selected');
  }
  return classes;
}

function handleCellClick(node: unknown, column: ColumnDef): void {
  if (!isCellClickable(node, column)) {
    return;
  }
  const payload = typeof column?.payload === 'function' ? column.payload(node) : null;
  emit('cell-click', { node, column, payload });
}

function handleRowClick(node: unknown): void {
  const n = node as Record<string, unknown> | null | undefined;
  if (!n?.rowClickable) {
    return;
  }
  emit('cell-click', {
    node,
    column: null,
    payload: n.rowPayload || null,
  });
}

function handleToggleRow(rowId: string): void {
  emit('toggle-row', rowId);
}

function handleToggleAll(expand: boolean): void {
  emit('toggle-all', expand);
}
</script>

<template>
  <div class="hierarchy-table-wrap">
    <div v-if="showToolbar" class="table-tree-actions">
      <button type="button" class="btn-sm" @click="handleToggleAll(true)">全部展開</button>
      <button type="button" class="btn-sm" @click="handleToggleAll(false)">全部收合</button>
    </div>

    <table class="matrix-table">
      <thead>
        <tr>
          <th>{{ resolvedNameColumnLabel }}</th>
          <th v-for="column in resolvedColumns" :key="column.key" :class="column.headerClass || ''">
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="hasRows">
          <template v-for="(group, groupIndex) in resolvedHierarchy" :key="getNodeId(group, 'root', groupIndex, 0)">
            <tr :class="getRowClasses(group, 0)" @click="handleRowClick(group)">
              <td>
                <span class="row-name">
                  <button
                    v-if="hasChildren(group)"
                    type="button"
                    class="expand-btn"
                    :class="{ expanded: isExpanded(group, getNodeId(group, 'root', groupIndex, 0)) }"
                    @click.stop="handleToggleRow(getNodeId(group, 'root', groupIndex, 0))"
                  >
                    ▶
                  </button>
                  <span v-else class="expand-placeholder"></span>
                  <span>{{ getNodeLabel(group) }}</span>
                </span>
              </td>
              <td
                v-for="column in resolvedColumns"
                :key="`g-${getNodeId(group, 'root', groupIndex, 0)}-${column.key}`"
                :class="getCellClasses(group, column, getCellDisplay(group, column))"
                @click.stop="handleCellClick(group, column)"
              >
                <template v-for="cell in [getCellDisplay(group, column)]" :key="`gc-${column.key}`">
                  <span v-if="cell.badgeClass" :class="cell.badgeClass">{{ cell.text }}</span>
                  <template v-else>{{ cell.text }}</template>
                </template>
              </td>
            </tr>

            <template v-if="isExpanded(group, getNodeId(group, 'root', groupIndex, 0))">
              <template
                v-for="(family, familyIndex) in getNodeChildren(group)"
                :key="getNodeId(family, getNodeId(group, 'root', groupIndex, 0), familyIndex, 1)"
              >
                <tr :class="getRowClasses(family, 1)" @click="handleRowClick(family)">
                  <td>
                    <span class="row-name">
                      <button
                        v-if="hasChildren(family)"
                        type="button"
                        class="expand-btn"
                        :class="{
                          expanded: isExpanded(
                            family,
                            getNodeId(family, getNodeId(group, 'root', groupIndex, 0), familyIndex, 1)
                          ),
                        }"
                        @click.stop="handleToggleRow(
                          getNodeId(family, getNodeId(group, 'root', groupIndex, 0), familyIndex, 1)
                        )"
                      >
                        ▶
                      </button>
                      <span v-else class="expand-placeholder"></span>
                      <span>{{ getNodeLabel(family) }}</span>
                    </span>
                  </td>
                  <td
                    v-for="column in resolvedColumns"
                    :key="`f-${getNodeId(family, getNodeId(group, 'root', groupIndex, 0), familyIndex, 1)}-${column.key}`"
                    :class="getCellClasses(family, column, getCellDisplay(family, column))"
                    @click.stop="handleCellClick(family, column)"
                  >
                    <template v-for="cell in [getCellDisplay(family, column)]" :key="`fc-${column.key}`">
                      <span v-if="cell.badgeClass" :class="cell.badgeClass">{{ cell.text }}</span>
                      <template v-else>{{ cell.text }}</template>
                    </template>
                  </td>
                </tr>

                <template
                  v-if="isExpanded(
                    family,
                    getNodeId(family, getNodeId(group, 'root', groupIndex, 0), familyIndex, 1)
                  )"
                >
                  <tr
                    v-for="(resource, resourceIndex) in getNodeChildren(family)"
                    :key="getNodeId(resource, getNodeId(family, getNodeId(group, 'root', groupIndex, 0), familyIndex, 1), resourceIndex, 2)"
                    :class="getRowClasses(resource, 2)"
                    @click="handleRowClick(resource)"
                  >
                    <td>
                      <span class="row-name">
                        <span class="expand-placeholder"></span>
                        <span>{{ getNodeLabel(resource) }}</span>
                      </span>
                    </td>
                    <td
                      v-for="column in resolvedColumns"
                      :key="`r-${getNodeId(resource, getNodeId(family, getNodeId(group, 'root', groupIndex, 0), familyIndex, 1), resourceIndex, 2)}-${column.key}`"
                      :class="getCellClasses(resource, column, getCellDisplay(resource, column))"
                      @click.stop="handleCellClick(resource, column)"
                    >
                      <template v-for="cell in [getCellDisplay(resource, column)]" :key="`rc-${column.key}`">
                        <span v-if="cell.badgeClass" :class="cell.badgeClass">{{ cell.text }}</span>
                        <template v-else>{{ cell.text }}</template>
                      </template>
                    </td>
                  </tr>
                </template>
              </template>
            </template>
          </template>
        </template>

        <tr v-else>
          <td :colspan="resolvedColumns.length + 1">
            <div class="empty-state">{{ resolvedEmptyText }}</div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
