<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';

interface HoldItem {
  lotId?: string | null;
  workorder?: string | null;
  product?: string | null;
  workcenter?: string | null;
  holdReason?: string | null;
  qty?: number | null;
  holdDate?: string | null;
  holdEmp?: string | null;
  holdComment?: string | null;
  releaseDate?: string | null;
  releaseEmp?: string | null;
  releaseComment?: string | null;
  holdHours?: number | null;
  ncr?: string | null;
  futureHoldComment?: string | null;
  package?: string | null;
}

interface Pagination {
  page?: number;
  perPage?: number;
  total?: number;
  totalPages?: number;
}

interface Props {
  // TODO: type — items can come from DuckDB (typed) or server (untyped); accept unknown for now
  items?: unknown[];
  pagination?: Pagination;
  loading?: boolean;
  paginating?: boolean;
  exporting?: boolean;
  errorMessage?: string;
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  pagination: () => ({ page: 1, perPage: 20, total: 0, totalPages: 1 }),
  loading: false,
  paginating: false,
  exporting: false,
  errorMessage: '',
});

const emit = defineEmits<{
  'prev-page': [];
  'next-page': [];
  export: [];
}>();

const pageSummary = computed(() => {
  const page = Number(props.pagination?.page || 1);
  const perPage = Number(props.pagination?.perPage || 20);
  const total = Number(props.pagination?.total || 0);

  if (total <= 0) return '顯示 0 / 0';

  const start = (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, total);
  return `顯示 ${start} - ${end} / ${total.toLocaleString('zh-TW')}`;
});

const pageInfo = computed(() => {
  const page = Number(props.pagination?.page || 1);
  const totalPages = Number(props.pagination?.totalPages || 1);
  return `Page ${page} / ${totalPages}`;
});

const tablePagination = computed(() => {
  const totalPages = Number(props.pagination?.totalPages || 1);
  if (totalPages <= 1) return null;
  return {
    page: Number(props.pagination?.page || 1),
    totalPages,
    infoText: pageInfo.value,
  };
});

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  return Number(value).toLocaleString('zh-TW');
}

function formatHours(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-';
  return Number(value).toFixed(2);
}

const tip = reactive({ visible: false, text: '', x: 0, y: 0 });

function showTip(event: MouseEvent): void {
  const target = event.currentTarget as HTMLElement;
  const text = target.getAttribute('data-tip');
  if (!text) return;
  const rect = target.getBoundingClientRect();
  tip.text = text;
  tip.x = rect.left;
  tip.y = rect.bottom + 4;
  tip.visible = true;
}

function hideTip(): void {
  tip.visible = false;
}

function handlePageChange(newPage: number): void {
  const currentPage = Number(props.pagination?.page || 1);
  if (newPage < currentPage) emit('prev-page');
  else if (newPage > currentPage) emit('next-page');
}

// ── Column resize ─────────────────────────────────────────────────────────────

interface ResizeState {
  thIndex: number;
  startX: number;
  startWidth: number;
}

const tableWrap = ref<HTMLElement | null>(null);
let resizeState: ResizeState | null = null;

function getThElements(): HTMLElement[] {
  if (!tableWrap.value) return [];
  return Array.from(tableWrap.value.querySelectorAll<HTMLElement>('table thead th'));
}

function getHandles(): HTMLElement[] {
  if (!tableWrap.value) return [];
  return Array.from(tableWrap.value.querySelectorAll<HTMLElement>('.col-resize-handle'));
}

function repositionHandles(): void {
  if (!tableWrap.value) return;
  const ths = getThElements();
  const handles = getHandles();
  const wrapRect = tableWrap.value.getBoundingClientRect();
  const scrollLeft = tableWrap.value.querySelector('.data-table-scroll')?.scrollLeft || 0;
  ths.forEach((th, i) => {
    const handle = handles[i];
    if (!handle) return;
    const rect = th.getBoundingClientRect();
    (handle as HTMLElement).style.left = `${rect.right - wrapRect.left + scrollLeft - 4}px`;
    (handle as HTMLElement).style.top = `${rect.top - wrapRect.top}px`;
    (handle as HTMLElement).style.height = `${rect.height}px`;
  });
}

function onPointerDown(e: PointerEvent, thIndex: number): void {
  e.preventDefault();
  const ths = getThElements();
  const th = ths[thIndex];
  if (!th) return;
  resizeState = {
    thIndex,
    startX: e.clientX,
    startWidth: th.offsetWidth,
  };
  document.addEventListener('pointermove', onPointerMove);
  document.addEventListener('pointerup', onPointerUp);
}

function onPointerMove(e: PointerEvent): void {
  if (!resizeState) return;
  const ths = getThElements();
  const th = ths[resizeState.thIndex];
  if (!th) return;
  const diff = e.clientX - resizeState.startX;
  const newWidth = Math.max(60, resizeState.startWidth + diff);
  th.style.width = `${newWidth}px`;
  th.style.minWidth = `${newWidth}px`;
}

function onPointerUp(): void {
  resizeState = null;
  document.removeEventListener('pointermove', onPointerMove);
  document.removeEventListener('pointerup', onPointerUp);
  repositionHandles();
}

function buildHandles(): void {
  if (!tableWrap.value) return;
  // Remove existing handles
  tableWrap.value.querySelectorAll('.col-resize-handle').forEach((h) => h.remove());

  const ths = getThElements();
  if (!ths.length || !window.PointerEvent) return; // fallback: no resize on non-pointer devices

  ths.forEach((_, i) => {
    const handle = document.createElement('div');
    handle.className = 'col-resize-handle';
    handle.setAttribute('aria-hidden', 'true');
    handle.addEventListener('pointerdown', (e) => onPointerDown(e, i));
    tableWrap.value!.appendChild(handle);
  });

  repositionHandles();
}

onMounted(() => {
  // Wait one tick for DataTable to render columns
  Promise.resolve().then(() => {
    buildHandles();
    const scrollEl = tableWrap.value?.querySelector('.data-table-scroll');
    scrollEl?.addEventListener('scroll', repositionHandles);
  });
});

onUnmounted(() => {
  document.removeEventListener('pointermove', onPointerMove);
  document.removeEventListener('pointerup', onPointerUp);
  const scrollEl = tableWrap.value?.querySelector('.data-table-scroll');
  scrollEl?.removeEventListener('scroll', repositionHandles);
});
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header detail-header">
      <div class="card-title ui-card-title">Hold / Release 明細</div>
      <div class="detail-header-actions">
        <div class="table-info">{{ pageSummary }}</div>
        <button
          type="button"
          class="ui-btn ui-btn--secondary"
          :class="{ 'is-loading': exporting }"
          :disabled="!pagination?.total || loading || exporting"
          @click="emit('export')"
        >
          {{ exporting ? '匯出中...' : '↓ 匯出 CSV' }}
        </button>
      </div>
    </div>

    <div class="card-body ui-card-body detail-card-body">
      <div ref="tableWrap" class="resizable-table-wrap">
        <DataTable
          :data="(items as Record<string, unknown>[])"
          :loading="loading || paginating"
          :pagination="tablePagination"
          @page-change="handlePageChange"
        >
          <DataTableColumn columnKey="lotId" label="Lot ID" :sortable="true" />
          <DataTableColumn columnKey="workorder" label="WorkOrder" :sortable="true" />
          <DataTableColumn columnKey="product" label="Product" :sortable="true" />
          <DataTableColumn columnKey="package" label="Package" :sortable="true" />
          <DataTableColumn columnKey="workcenter" label="站別" :sortable="true" />
          <DataTableColumn columnKey="holdReason" label="Hold Reason" :sortable="true" />
          <DataTableColumn columnKey="qty" label="數量" :sortable="true" align="right" />
          <DataTableColumn columnKey="holdDate" label="Hold 時間" :sortable="true" />
          <DataTableColumn columnKey="holdEmp" label="Hold 人員" :sortable="true" />
          <DataTableColumn columnKey="holdComment" label="Hold Comment" :sortable="true" />
          <DataTableColumn columnKey="releaseDate" label="Release 時間" :sortable="true" />
          <DataTableColumn columnKey="releaseEmp" label="Release 人員" :sortable="true" />
          <DataTableColumn columnKey="releaseComment" label="Release Comment" :sortable="true" />
          <DataTableColumn columnKey="holdHours" label="時長(hr)" :sortable="true" align="right" />
          <DataTableColumn columnKey="ncr" label="NCR" :sortable="true" />
          <DataTableColumn columnKey="futureHoldComment" label="Future Hold Comment" :sortable="true" />

          <template #cell="{ row, columnKey }">
            <template v-if="columnKey === 'lotId'">{{ row.lotId || '-' }}</template>
            <template v-else-if="columnKey === 'workorder'">{{ row.workorder || '-' }}</template>
            <template v-else-if="columnKey === 'product'">{{ row.product || '-' }}</template>
            <template v-else-if="columnKey === 'package'">{{ (row as HoldItem).package || '-' }}</template>
            <template v-else-if="columnKey === 'workcenter'">{{ row.workcenter || '-' }}</template>
            <template v-else-if="columnKey === 'holdReason'">{{ row.holdReason || '-' }}</template>
            <template v-else-if="columnKey === 'qty'">{{ formatNumber(row.qty) }}</template>
            <template v-else-if="columnKey === 'holdDate'">{{ row.holdDate || '-' }}</template>
            <template v-else-if="columnKey === 'holdEmp'">{{ row.holdEmp || '-' }}</template>
            <template v-else-if="columnKey === 'holdComment'">
              <span class="cell-comment" :data-tip="row.holdComment || ''" @mouseenter="showTip" @mouseleave="hideTip">{{ row.holdComment || '-' }}</span>
            </template>
            <template v-else-if="columnKey === 'releaseDate'">{{ row.releaseDate || '仍在 Hold' }}</template>
            <template v-else-if="columnKey === 'releaseEmp'">{{ row.releaseEmp || '-' }}</template>
            <template v-else-if="columnKey === 'releaseComment'">
              <span class="cell-comment" :data-tip="row.releaseComment || ''" @mouseenter="showTip" @mouseleave="hideTip">{{ row.releaseComment || '-' }}</span>
            </template>
            <template v-else-if="columnKey === 'holdHours'">{{ formatHours(row.holdHours) }}</template>
            <template v-else-if="columnKey === 'ncr'">{{ row.ncr || '-' }}</template>
            <template v-else-if="columnKey === 'futureHoldComment'">
              <span class="cell-comment" :data-tip="row.futureHoldComment || ''" @mouseenter="showTip" @mouseleave="hideTip">{{ row.futureHoldComment || '-' }}</span>
            </template>
          </template>
        </DataTable>
      </div>
    </div>
  </section>

  <Teleport to="body">
    <div class="theme-hold-history">
      <div v-if="tip.visible" class="cell-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
        {{ tip.text }}
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Flat-table layout: remove card-body padding so DataTable extends flush to card edges */
.detail-card-body {
  padding: 0;
}

.detail-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

</style>
