<script setup lang="ts">
import { computed, provide, ref, toRef } from 'vue'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-vue-next'
import { useSortableTable } from '../../shared-composables/useSortableTable'
import EmptyState from './EmptyState.vue'
import PaginationControl from './PaginationControl.vue'

interface ColumnDefinition {
  key: string;
  label: string;
  sortable: boolean;
  width: string | null;
  align: string;
}

interface PaginationShape {
  page: number;
  totalPages: number;
  infoText?: string;
}

interface Props {
  data?: Record<string, unknown>[];
  loading?: boolean;
  pagination?: PaginationShape | null;
  serverSort?: boolean;
  emptyType?: string;
  /** When set, overrides the internal sort-key display (use to reset indicator after new query). */
  controlledSortKey?: string;
  /** When set, overrides the internal sort-direction display. */
  controlledSortDir?: string;
}

const props = withDefaults(defineProps<Props>(), {
  data: () => [],
  loading: false,
  pagination: null,
  serverSort: false,
  emptyType: 'no-data',
  controlledSortKey: undefined,
  controlledSortDir: undefined,
});

const emit = defineEmits<{
  (e: 'sort', payload: { key: string; direction: string }): void;
  (e: 'page-change', page: number): void;
}>();

// --- Column registry ---
const columns = ref<ColumnDefinition[]>([])

provide('registerColumn', (col: ColumnDefinition) => {
  columns.value.push(col)
})
provide('unregisterColumn', (key: string) => {
  const idx = columns.value.findIndex((c) => c.key === key)
  if (idx !== -1) columns.value.splice(idx, 1)
})

// --- Sorting ---
const dataRef = toRef(props, 'data')
const { sortKey, sortDirection, sortedData, setSortKey } = useSortableTable(dataRef)

function handleSort(col: ColumnDefinition) {
  if (!col.sortable) return
  if (props.serverSort) {
    // Toggle direction for same key
    const newDir =
      sortKey.value === col.key && sortDirection.value === 'asc' ? 'desc' : 'asc'
    sortKey.value = col.key
    sortDirection.value = newDir
    emit('sort', { key: col.key, direction: newDir })
  } else {
    setSortKey(col.key)
  }
}

// Effective sort key/dir for display: prefer controlled props (server-driven), fall back to internal
const effectiveSortKey = computed(() =>
  props.controlledSortKey !== undefined ? props.controlledSortKey : sortKey.value
)
const effectiveSortDir = computed(() =>
  props.controlledSortDir !== undefined ? props.controlledSortDir : sortDirection.value
)

function sortIcon(col: ColumnDefinition) {
  if (!col.sortable) return null
  if (effectiveSortKey.value !== col.key) return ArrowUpDown
  return effectiveSortDir.value === 'asc' ? ArrowUp : ArrowDown
}

// --- Expandable rows ---
const expandedRow = ref<number | null>(null)

function toggleExpand(index: number) {
  expandedRow.value = expandedRow.value === index ? null : index
}

// --- Computed display data ---
const displayData = computed(() => {
  if (props.serverSort) return props.data
  return sortedData.value
})

const isEmpty = computed(() => !props.loading && displayData.value.length === 0)
</script>

<template>
  <!-- Column registrations (invisible) -->
  <slot />

  <div class="data-table-root">
    <div
      class="data-table-scroll"
      :class="{ 'is-loading': loading }"
    >
      <table class="data-table">
        <thead class="data-table-head">
          <tr>
            <!-- Expand toggle column -->
            <th
              v-if="$slots.expand"
              class="data-table-th data-table-th--expand"
              aria-label="展開"
            />
            <th
              v-for="col in columns"
              :key="col.key"
              class="data-table-th"
              :class="[
                `data-table-th--${col.align || 'left'}`,
                { 'data-table-th--sortable': col.sortable }
              ]"
              :style="col.width ? { width: col.width } : {}"
              :aria-sort="
                col.sortable && effectiveSortKey === col.key
                  ? effectiveSortDir === 'asc'
                    ? 'ascending'
                    : 'descending'
                  : col.sortable
                  ? 'none'
                  : undefined
              "
              @click="handleSort(col)"
            >
              <span class="data-table-th-inner">
                {{ col.label }}
                <component
                  :is="sortIcon(col)"
                  v-if="sortIcon(col)"
                  class="data-table-sort-icon"
                  :class="{ 'data-table-sort-icon--active': effectiveSortKey === col.key }"
                  :size="14"
                />
              </span>
            </th>
          </tr>
        </thead>

        <tbody v-if="!isEmpty">
          <template v-for="(row, index) in displayData" :key="index">
            <tr class="data-table-row" :class="{ 'data-table-row--even': index % 2 === 1 }">
              <!-- Expand toggle cell -->
              <td v-if="$slots.expand" class="data-table-td data-table-td--expand">
                <button
                  type="button"
                  class="data-table-expand-btn"
                  :aria-expanded="expandedRow === index"
                  @click="toggleExpand(index)"
                >
                  <svg
                    class="data-table-expand-icon"
                    :class="{ 'data-table-expand-icon--open': expandedRow === index }"
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="none"
                  >
                    <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </td>

              <td
                v-for="col in columns"
                :key="col.key"
                class="data-table-td"
                :class="`data-table-td--${col.align || 'left'}`"
              >
                <slot
                  name="cell"
                  :column-key="col.key"
                  :row="row"
                  :value="row[col.key]"
                  :index="index"
                >
                  {{ row[col.key] }}
                </slot>
              </td>
            </tr>

            <!-- Expand row -->
            <tr
              v-if="$slots.expand && expandedRow === index"
              :key="`expand-${index}`"
              class="data-table-expand-row"
            >
              <td :colspan="columns.length + 1" class="data-table-expand-td">
                <slot name="expand" :row="row" :index="index" />
              </td>
            </tr>
          </template>
        </tbody>

        <tbody v-else>
          <tr>
            <td
              :colspan="($slots.expand ? 1 : 0) + columns.length"
              class="data-table-empty-cell"
            >
              <EmptyState :type="emptyType as 'no-data' | 'filter-empty' | 'error' | 'loading'" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination footer -->
    <div v-if="pagination" class="data-table-footer">
      <PaginationControl
        :page="pagination.page"
        :total-pages="pagination.totalPages"
        :info-text="pagination.infoText || ''"
        @change="(page) => emit('page-change', page)"
        @prev="(page) => emit('page-change', page)"
        @next="(page) => emit('page-change', page)"
      />
    </div>
  </div>
</template>

<style scoped>
.data-table-root {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.data-table-scroll {
  overflow-x: auto;
  transition: opacity var(--motion-normal) var(--motion-ease);
}

.data-table-scroll.is-loading {
  opacity: 0.4;
  pointer-events: none;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  color: theme('colors.text.primary');
}

.data-table-head {
  position: sticky;
  top: 0;
  z-index: 10;
  background: theme('colors.surface.muted');
  box-shadow: 0 1px 0 theme('colors.stroke.soft');
}

.data-table-th {
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 700;
  color: theme('colors.text.subtle');
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid theme('colors.stroke.soft');
  user-select: none;
}

.data-table-th--center { text-align: center; }
.data-table-th--right  { text-align: right; }
.data-table-th--expand { width: 36px; padding: 0; }

.data-table-th--sortable {
  cursor: pointer;
}
.data-table-th--sortable:hover {
  background: theme('colors.surface.hover');
  color: theme('colors.text.primary');
}

.data-table-th-inner {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.data-table-sort-icon {
  opacity: 0.35;
  flex-shrink: 0;
}
.data-table-sort-icon--active {
  opacity: 1;
  color: theme('colors.brand.500');
}

.data-table-row {
  border-bottom: 1px solid theme('colors.stroke.soft');
  transition: background var(--motion-fast) var(--motion-ease);
}

.data-table-row:hover {
  background: theme('colors.surface.hover');
}

.data-table-row--even {
  background: theme('colors.surface.muted');
}
.data-table-row--even:hover {
  background: theme('colors.surface.hover');
}

.data-table-td {
  padding: 9px 12px;
  font-size: 13px;
  vertical-align: middle;
  white-space: nowrap;
}

.data-table-td--center { text-align: center; }
.data-table-td--right  { text-align: right; }
.data-table-td--expand { width: 36px; padding: 4px; text-align: center; }

.data-table-expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 4px;
  color: theme('colors.text.secondary');
  transition: background var(--motion-fast);
}
.data-table-expand-btn:hover {
  background: theme('colors.surface.hover');
}

.data-table-expand-icon {
  transition: transform var(--motion-fast) var(--motion-ease);
}
.data-table-expand-icon--open {
  transform: rotate(90deg);
}

.data-table-expand-row {
  background: theme('colors.surface.muted');
}

.data-table-expand-td {
  padding: 12px 16px;
  border-bottom: 1px solid theme('colors.stroke.soft');
}

.data-table-empty-cell {
  padding: 0;
  text-align: center;
}

.data-table-footer {
  display: flex;
  justify-content: flex-end;
  padding: 10px 12px;
  border-top: 1px solid theme('colors.stroke.soft');
  background: theme('colors.surface.muted');
}
</style>
