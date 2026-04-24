<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import DataTable from '../../shared-ui/components/DataTable.vue';
import DataTableColumn from '../../shared-ui/components/DataTableColumn.vue';

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  pagination: {
    type: Object,
    default: () => ({ page: 1, perPage: 20, total: 0, totalPages: 1 }),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  paginating: {
    type: Boolean,
    default: false,
  },
  exporting: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['prev-page', 'next-page', 'export']);

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

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '-';
  return Number(value).toLocaleString('zh-TW');
}

function formatHours(value) {
  if (value === null || value === undefined || value === '') return '-';
  return Number(value).toFixed(2);
}

const tip = reactive({ visible: false, text: '', x: 0, y: 0 });

function showTip(event) {
  const text = event.currentTarget.getAttribute('data-tip');
  if (!text) return;
  const rect = event.currentTarget.getBoundingClientRect();
  tip.text = text;
  tip.x = rect.left;
  tip.y = rect.bottom + 4;
  tip.visible = true;
}

function hideTip() {
  tip.visible = false;
}

function handlePageChange(newPage) {
  const currentPage = Number(props.pagination?.page || 1);
  if (newPage < currentPage) emit('prev-page');
  else if (newPage > currentPage) emit('next-page');
}

// ── Column resize ─────────────────────────────────────────────────────────────

const tableWrap = ref(null);
let resizeState = null;

function getThElements() {
  if (!tableWrap.value) return [];
  return Array.from(tableWrap.value.querySelectorAll('table thead th'));
}

function getHandles() {
  if (!tableWrap.value) return [];
  return Array.from(tableWrap.value.querySelectorAll('.col-resize-handle'));
}

function repositionHandles() {
  const ths = getThElements();
  const handles = getHandles();
  ths.forEach((th, i) => {
    const handle = handles[i];
    if (!handle) return;
    const rect = th.getBoundingClientRect();
    const wrapRect = tableWrap.value.getBoundingClientRect();
    const scrollLeft = tableWrap.value.querySelector('.data-table-scroll')?.scrollLeft || 0;
    handle.style.left = `${rect.right - wrapRect.left + scrollLeft - 4}px`;
    handle.style.top = `${rect.top - wrapRect.top}px`;
    handle.style.height = `${rect.height}px`;
  });
}

function onPointerDown(e, thIndex) {
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

function onPointerMove(e) {
  if (!resizeState) return;
  const ths = getThElements();
  const th = ths[resizeState.thIndex];
  if (!th) return;
  const diff = e.clientX - resizeState.startX;
  const newWidth = Math.max(60, resizeState.startWidth + diff);
  th.style.width = `${newWidth}px`;
  th.style.minWidth = `${newWidth}px`;
}

function onPointerUp() {
  resizeState = null;
  document.removeEventListener('pointermove', onPointerMove);
  document.removeEventListener('pointerup', onPointerUp);
  repositionHandles();
}

function buildHandles() {
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
    tableWrap.value.appendChild(handle);
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
          class="export-csv-btn"
          :disabled="!pagination?.total || loading || exporting"
          @click="emit('export')"
        >
          {{ exporting ? '匯出中...' : '↓ 匯出 CSV' }}
        </button>
      </div>
    </div>

    <div class="card-body ui-card-body">
      <div ref="tableWrap" class="resizable-table-wrap">
        <DataTable
          :data="items"
          :loading="loading || paginating"
          :pagination="tablePagination"
          @page-change="handlePageChange"
        >
          <DataTableColumn columnKey="lotId" label="Lot ID" :sortable="true" />
          <DataTableColumn columnKey="workorder" label="WorkOrder" :sortable="true" />
          <DataTableColumn columnKey="product" label="Product" :sortable="true" />
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
    <div v-if="tip.visible" class="cell-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      {{ tip.text }}
    </div>
  </Teleport>
</template>

<style scoped>
.detail-header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.export-csv-btn {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid #0080C8;
  border-radius: 6px;
  background: transparent;
  color: #0080C8;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}

.export-csv-btn:hover:not(:disabled) {
  background: #0080C8;
  color: #fff;
}

.export-csv-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
