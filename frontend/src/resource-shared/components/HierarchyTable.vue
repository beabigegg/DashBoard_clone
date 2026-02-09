<script setup>
import { computed } from 'vue';

const props = defineProps({
  hierarchy: {
    type: Array,
    default: () => [],
  },
  columns: {
    type: Array,
    default: () => [],
  },
  expandedState: {
    type: Object,
    default: () => ({}),
  },
  nameColumnLabel: {
    type: String,
    default: '名稱',
  },
  emptyText: {
    type: String,
    default: '無資料',
  },
  showToolbar: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['cell-click', 'toggle-row', 'toggle-all']);

const hasRows = computed(() => Array.isArray(props.hierarchy) && props.hierarchy.length > 0);

function getNodeChildren(node) {
  if (!node || typeof node !== 'object') {
    return [];
  }
  if (Array.isArray(node.children)) {
    return node.children;
  }
  if (Array.isArray(node.families)) {
    return node.families;
  }
  if (Array.isArray(node.resources)) {
    return node.resources;
  }
  if (Array.isArray(node.equipment)) {
    return node.equipment;
  }
  return [];
}

function getNodeId(node, parentId, index, level) {
  if (node?.id) {
    return String(node.id);
  }
  if (node?.rowId) {
    return String(node.rowId);
  }
  return `${parentId || 'row'}_${level}_${index}`;
}

function hasChildren(node) {
  return getNodeChildren(node).length > 0;
}

function isExpanded(node, rowId) {
  if (!hasChildren(node)) {
    return false;
  }
  return Boolean(props.expandedState?.[rowId]);
}

function getNodeLabel(node) {
  return node?.name || node?.label || '--';
}

function getIndentClass(level) {
  if (level === 1) {
    return 'indent-1';
  }
  if (level === 2) {
    return 'indent-2';
  }
  return '';
}

function getRowClasses(node, level) {
  const classes = [`row-level-${level}`];
  const indentClass = getIndentClass(level);
  if (indentClass) {
    classes.push(indentClass);
  }
  if (node?.rowClass) {
    classes.push(node.rowClass);
  }
  if (node?.rowClickable) {
    classes.push('clickable-row');
  }
  if (node?.rowSelected) {
    classes.push('selected');
  }
  return classes;
}

function resolveCellValue(node, column) {
  if (typeof column?.value === 'function') {
    return column.value(node);
  }
  if (node?.values && Object.prototype.hasOwnProperty.call(node.values, column.key)) {
    return node.values[column.key];
  }
  if (Object.prototype.hasOwnProperty.call(node || {}, column.key)) {
    return node[column.key];
  }
  return '';
}

function getCellDisplay(node, column) {
  const rendered = typeof column?.render === 'function' ? column.render(node) : resolveCellValue(node, column);
  if (rendered && typeof rendered === 'object' && !Array.isArray(rendered)) {
    return {
      text: rendered.text ?? rendered.value ?? '',
      badgeClass: rendered.badgeClass || '',
    };
  }
  return {
    text: rendered ?? '',
    badgeClass: '',
  };
}

function isCellClickable(node, column) {
  if (typeof column?.isClickable === 'function') {
    return Boolean(column.isClickable(node));
  }
  return Boolean(column?.clickable);
}

function isCellSelected(node, column) {
  if (typeof column?.isSelected === 'function') {
    return Boolean(column.isSelected(node));
  }
  return Boolean(node?.selectedColumns && node.selectedColumns[column?.key]);
}

function getCellClasses(node, column, display) {
  const classes = [];
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

function handleCellClick(node, column) {
  if (!isCellClickable(node, column)) {
    return;
  }
  const payload = typeof column?.payload === 'function' ? column.payload(node) : null;
  emit('cell-click', { node, column, payload });
}

function handleRowClick(node) {
  if (!node?.rowClickable) {
    return;
  }
  emit('cell-click', {
    node,
    column: null,
    payload: node.rowPayload || null,
  });
}

function handleToggleRow(rowId) {
  emit('toggle-row', rowId);
}

function handleToggleAll(expand) {
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
          <th>{{ nameColumnLabel }}</th>
          <th v-for="column in columns" :key="column.key" :class="column.headerClass || ''">
            {{ column.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-if="hasRows">
          <template v-for="(group, groupIndex) in hierarchy" :key="getNodeId(group, 'root', groupIndex, 0)">
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
                v-for="column in columns"
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
                    v-for="column in columns"
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
                      v-for="column in columns"
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
          <td :colspan="columns.length + 1">
            <div class="empty-state">{{ emptyText }}</div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
