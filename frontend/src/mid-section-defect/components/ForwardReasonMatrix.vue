<script setup lang="ts">
import { computed, ref } from 'vue';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MatrixDim {
  name: string;
  total: number;
}

interface FrontDownstreamReasonMatrix {
  rows: MatrixDim[];
  cols: MatrixDim[];
  cells: number[][];
  row_pct: number[][];
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

const props = defineProps<{
  matrix?: FrontDownstreamReasonMatrix | null;
  highlightRow?: string | null;
}>();

// ---------------------------------------------------------------------------
// Mode toggle: 占比 (default) | 數量
// ---------------------------------------------------------------------------

type ViewMode = 'pct' | 'qty';
const mode = ref<ViewMode>('pct');

// ---------------------------------------------------------------------------
// Derived data
// ---------------------------------------------------------------------------

const isEmpty = computed((): boolean => {
  const m = props.matrix;
  return !m || !Array.isArray(m.rows) || m.rows.length === 0 || !Array.isArray(m.cols) || m.cols.length === 0;
});

/**
 * Maximum cell value across all cells (for qty-mode shading).
 */
const maxCell = computed((): number => {
  const m = props.matrix;
  if (!m?.cells) return 1;
  let max = 0;
  for (const row of m.cells) {
    for (const v of row) {
      if (v > max) max = v;
    }
  }
  return max || 1;
});

/**
 * Compute inline style for a cell based on intensity (0..1).
 * brand.500 = indigo-500 = rgb(99,102,241) — derived from tailwind token,
 * expressed as rgba() literal to avoid CSS var() indirection limitation.
 */
function cellBgStyle(intensity: number): Record<string, string> {
  if (intensity <= 0) return {};
  const alpha = Number((Math.min(intensity, 1) * 0.6).toFixed(3));
  return { backgroundColor: `rgba(99,102,241,${alpha})` };
}

function getCellPct(ri: number, ci: number): number {
  return props.matrix?.row_pct?.[ri]?.[ci] ?? 0;
}

function getCellQty(ri: number, ci: number): number {
  return props.matrix?.cells?.[ri]?.[ci] ?? 0;
}

function getRowTotal(ri: number): number {
  return props.matrix?.rows?.[ri]?.total ?? 0;
}

function getColTotal(ci: number): number {
  return props.matrix?.cols?.[ci]?.total ?? 0;
}

function pctIntensity(ri: number, ci: number): number {
  return Math.min(getCellPct(ri, ci) / 100, 1);
}

function qtyIntensity(ri: number, ci: number): number {
  return getCellQty(ri, ci) / maxCell.value;
}

function cellStyle(ri: number, ci: number): Record<string, string> {
  const intensity = mode.value === 'pct' ? pctIntensity(ri, ci) : qtyIntensity(ri, ci);
  return cellBgStyle(intensity);
}

function cellText(ri: number, ci: number): string {
  if (mode.value === 'pct') {
    const v = getCellPct(ri, ci);
    return v > 0 ? `${v.toFixed(0)}%` : '—';
  } else {
    const v = getCellQty(ri, ci);
    return v > 0 ? v.toLocaleString() : '—';
  }
}
</script>

<template>
  <div class="frm-root">
    <!-- Header row -->
    <div class="frm-header">
      <h2 class="frm-title">前段報廢原因 × 下游報廢原因 關聯</h2>
      <div class="frm-toggle-group" role="group" aria-label="顯示模式">
        <button
          type="button"
          class="hero-toggle-btn"
          :class="{ active: mode === 'pct' }"
          :aria-pressed="mode === 'pct'"
          data-testid="matrix-mode-pct"
          @click="mode = 'pct'"
        >
          占比
        </button>
        <button
          type="button"
          class="hero-toggle-btn"
          :class="{ active: mode === 'qty' }"
          :aria-pressed="mode === 'qty'"
          data-testid="matrix-mode-qty"
          @click="mode = 'qty'"
        >
          數量
        </button>
      </div>
    </div>

    <!-- Semantics note -->
    <p class="frm-hint">
      同一批次可能屬於多個前段原因（Cohort），各列加總可超過報廢批次總數；預設顯示列內占比（Row%）。
    </p>

    <!-- Empty state -->
    <div v-if="isEmpty" class="frm-empty" role="status" data-testid="matrix-empty">
      暫無資料
    </div>

    <!-- Matrix table -->
    <div v-else class="frm-table-wrapper">
      <table
        class="frm-table"
        role="table"
        aria-label="前段報廢原因與下游報廢原因關聯矩陣"
        data-testid="matrix-table"
      >
        <thead>
          <tr>
            <th scope="col" class="frm-th-corner">前段原因 ╲ 下游原因</th>
            <th
              v-for="(col, ci) in matrix!.cols"
              :key="`col-${ci}`"
              scope="col"
              class="frm-th-col"
            >
              {{ col.name }}
            </th>
            <th scope="col" class="frm-th-rowtotal">合計</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in matrix!.rows"
            :key="`row-${ri}`"
            :class="{ 'frm-row-highlight': highlightRow && highlightRow === row.name }"
          >
            <th scope="row" class="frm-th-row">{{ row.name }}</th>
            <td
              v-for="(_col, ci) in matrix!.cols"
              :key="`cell-${ri}-${ci}`"
              class="frm-td"
              :style="cellStyle(ri, ci)"
            >
              {{ cellText(ri, ci) }}
            </td>
            <td class="frm-td frm-td-total">
              {{ getRowTotal(ri).toLocaleString() }}
            </td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <th scope="row" class="frm-th-row frm-tf-label">下游合計</th>
            <td
              v-for="(_col, ci) in matrix!.cols"
              :key="`coltotal-${ci}`"
              class="frm-td frm-td-total"
            >
              {{ getColTotal(ci).toLocaleString() }}
            </td>
            <td class="frm-td frm-td-total"></td>
          </tr>
        </tfoot>
      </table>
    </div>
  </div>
</template>

<style scoped>
/*
 * All rules here are scoped to this component (Vue scoped CSS).
 * CSS custom properties (--msd-*) are resolved from .theme-mid-section-defect
 * declared in style.css — they cascade into scoped rules.
 * We avoid theme() here in favour of CSS vars to stay safe with PostCSS scoping.
 */

.frm-root {
  background: var(--msd-card-bg);
  border-radius: 12px;
  box-shadow: var(--msd-shadow);
  padding: 1rem 1.25rem;
}

.frm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}

.frm-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--msd-text);
}

.frm-toggle-group {
  display: flex;
  gap: 0.5rem;
}

.frm-hint {
  font-size: 12px;
  color: var(--msd-muted);
  margin: 0 0 0.75rem;
  line-height: 1.5;
}

.frm-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  font-size: 14px;
  color: var(--msd-muted);
}

.frm-table-wrapper {
  overflow-x: auto;
  border: 1px solid var(--msd-border);
  border-radius: 8px;
}

.frm-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.frm-th-corner,
.frm-th-col,
.frm-th-rowtotal {
  background: theme('colors.surface.hover');
  padding: 0.375rem 0.75rem;
  font-weight: 600;
  font-size: 12px;
  color: theme('colors.text.subtle');
  white-space: nowrap;
  border-bottom: 2px solid var(--msd-border);
}

.frm-th-corner {
  text-align: left;
  position: sticky;
  left: 0;
  z-index: 2;
}

.frm-th-col {
  text-align: center;
  min-width: 80px;
}

.frm-th-rowtotal {
  text-align: right;
}

.frm-th-row {
  background: theme('colors.surface.hover');
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-weight: 500;
  font-size: 12px;
  color: theme('colors.text.subtle');
  white-space: nowrap;
  border-bottom: 1px solid theme('colors.surface.hover');
  position: sticky;
  left: 0;
  z-index: 1;
}

.frm-tf-label {
  font-weight: 600;
  border-top: 2px solid var(--msd-border);
}

.frm-td {
  padding: 0.5rem 0.75rem;
  text-align: center;
  border-bottom: 1px solid theme('colors.surface.hover');
  font-variant-numeric: tabular-nums;
  transition: background-color 0.15s ease;
}

.frm-td-total {
  text-align: right;
  font-weight: 600;
  color: theme('colors.text.subtle');
  background: theme('colors.surface.muted');
}

tbody tr:hover .frm-td:not(.frm-td-total) {
  filter: brightness(0.95);
}

.frm-row-highlight .frm-th-row,
.frm-row-highlight .frm-td:not(.frm-td-total) {
  background-color: rgba(99, 102, 241, 0.06);
}
</style>
