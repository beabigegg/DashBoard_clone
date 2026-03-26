<script setup>
import { computed, reactive } from 'vue';
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
  errorMessage: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['prev-page', 'next-page']);

const pageSummary = computed(() => {
  const page = Number(props.pagination?.page || 1);
  const perPage = Number(props.pagination?.perPage || 20);
  const total = Number(props.pagination?.total || 0);

  if (total <= 0) {
    return '顯示 0 / 0';
  }

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
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return Number(value).toLocaleString('zh-TW');
}

function formatHours(value) {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  return Number(value).toFixed(2);
}

const tip = reactive({ visible: false, text: '', x: 0, y: 0 });

function showTip(event) {
  const text = event.currentTarget.getAttribute('data-tip');
  if (!text) {
    return;
  }
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
  if (newPage < currentPage) {
    emit('prev-page');
  } else if (newPage > currentPage) {
    emit('next-page');
  }
}
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header detail-header">
      <div class="card-title ui-card-title">Hold / Release 明細</div>
      <div class="table-info">{{ pageSummary }}</div>
    </div>

    <div class="card-body ui-card-body">
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

        <template #cell="{ row, columnKey, value }">
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
  </section>

  <Teleport to="body">
    <div v-if="tip.visible" class="cell-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      {{ tip.text }}
    </div>
  </Teleport>
</template>
