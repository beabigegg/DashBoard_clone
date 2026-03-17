<script setup>
import { computed, reactive } from 'vue';
import { useSortableTable } from '../../shared-composables/useSortableTable.js';
import Pagination from '../../shared-ui/components/PaginationControl.vue';

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

const itemsRef = computed(() => props.items);
const { sortKey, sortDirection, sortedData, toggleSort } = useSortableTable(itemsRef);

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
</script>

<template>
  <section class="card ui-card">
    <div class="card-header ui-card-header detail-header">
      <div class="card-title ui-card-title">Hold / Release 明細</div>
      <div class="table-info">{{ pageSummary }}</div>
    </div>

    <div class="card-body ui-card-body detail-table-wrap" :class="{ paginating: paginating }">
      <table class="detail-table">
        <thead>
          <tr>
            <th class="cursor-pointer" @click="toggleSort('lotId')" :aria-sort="sortKey === 'lotId' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Lot ID <span>{{ sortKey === 'lotId' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('workorder')" :aria-sort="sortKey === 'workorder' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">WorkOrder <span>{{ sortKey === 'workorder' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('product')" :aria-sort="sortKey === 'product' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Product <span>{{ sortKey === 'product' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('workcenter')" :aria-sort="sortKey === 'workcenter' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">站別 <span>{{ sortKey === 'workcenter' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdReason')" :aria-sort="sortKey === 'holdReason' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Hold Reason <span>{{ sortKey === 'holdReason' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('qty')" :aria-sort="sortKey === 'qty' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">數量 <span>{{ sortKey === 'qty' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdDate')" :aria-sort="sortKey === 'holdDate' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Hold 時間 <span>{{ sortKey === 'holdDate' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdEmp')" :aria-sort="sortKey === 'holdEmp' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Hold 人員 <span>{{ sortKey === 'holdEmp' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdComment')" :aria-sort="sortKey === 'holdComment' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Hold Comment <span>{{ sortKey === 'holdComment' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('releaseDate')" :aria-sort="sortKey === 'releaseDate' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Release 時間 <span>{{ sortKey === 'releaseDate' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('releaseEmp')" :aria-sort="sortKey === 'releaseEmp' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Release 人員 <span>{{ sortKey === 'releaseEmp' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('releaseComment')" :aria-sort="sortKey === 'releaseComment' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Release Comment <span>{{ sortKey === 'releaseComment' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('holdHours')" :aria-sort="sortKey === 'holdHours' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">時長(hr) <span>{{ sortKey === 'holdHours' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('ncr')" :aria-sort="sortKey === 'ncr' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">NCR <span>{{ sortKey === 'ncr' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
            <th class="cursor-pointer" @click="toggleSort('futureHoldComment')" :aria-sort="sortKey === 'futureHoldComment' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'">Future Hold Comment <span>{{ sortKey === 'futureHoldComment' ? (sortDirection === 'asc' ? '▲' : '▼') : '⇕' }}</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="15" class="placeholder">Loading...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="15" class="placeholder">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="sortedData.length === 0">
            <td colspan="15" class="placeholder">No data</td>
          </tr>
          <tr v-for="item in sortedData" v-else :key="`${item.lotId}-${item.holdDate}-${item.releaseDate}`">
            <td>{{ item.lotId || '-' }}</td>
            <td>{{ item.workorder || '-' }}</td>
            <td>{{ item.product || '-' }}</td>
            <td>{{ item.workcenter || '-' }}</td>
            <td>{{ item.holdReason || '-' }}</td>
            <td>{{ formatNumber(item.qty) }}</td>
            <td>{{ item.holdDate || '-' }}</td>
            <td>{{ item.holdEmp || '-' }}</td>
            <td class="cell-comment" :data-tip="item.holdComment || ''" @mouseenter="showTip" @mouseleave="hideTip">{{ item.holdComment || '-' }}</td>
            <td>{{ item.releaseDate || '仍在 Hold' }}</td>
            <td>{{ item.releaseEmp || '-' }}</td>
            <td class="cell-comment" :data-tip="item.releaseComment || ''" @mouseenter="showTip" @mouseleave="hideTip">{{ item.releaseComment || '-' }}</td>
            <td>{{ formatHours(item.holdHours) }}</td>
            <td>{{ item.ncr || '-' }}</td>
            <td class="cell-comment" :data-tip="item.futureHoldComment || ''" @mouseenter="showTip" @mouseleave="hideTip">{{ item.futureHoldComment || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <Pagination
      :visible="Number(pagination.totalPages || 1) > 1"
      :page="Number(pagination.page || 1)"
      :total-pages="Number(pagination.totalPages || 1)"
      :info-text="pageInfo"
      @prev="emit('prev-page')"
      @next="emit('next-page')"
    />
  </section>

  <Teleport to="body">
    <div v-if="tip.visible" class="cell-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      {{ tip.text }}
    </div>
  </Teleport>
</template>
