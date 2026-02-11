<script setup>
import { computed, reactive } from 'vue';

const props = defineProps({
  items: {
    type: Array,
    default: () => [],
  },
  pagination: {
    type: Object,
    default: () => ({ page: 1, perPage: 50, total: 0, totalPages: 1 }),
  },
  loading: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['prev-page', 'next-page']);

const canPrev = computed(() => Number(props.pagination?.page || 1) > 1);
const canNext = computed(() => Number(props.pagination?.page || 1) < Number(props.pagination?.totalPages || 1));

const pageSummary = computed(() => {
  const page = Number(props.pagination?.page || 1);
  const perPage = Number(props.pagination?.perPage || 50);
  const total = Number(props.pagination?.total || 0);

  if (total <= 0) {
    return '顯示 0 / 0';
  }

  const start = (page - 1) * perPage + 1;
  const end = Math.min(page * perPage, total);
  return `顯示 ${start} - ${end} / ${total.toLocaleString('zh-TW')}`;
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
  <section class="card">
    <div class="card-header detail-header">
      <div class="card-title">Hold / Release 明細</div>
      <div class="table-info">{{ pageSummary }}</div>
    </div>

    <div class="card-body detail-table-wrap">
      <table class="detail-table">
        <thead>
          <tr>
            <th>Lot ID</th>
            <th>WorkOrder</th>
            <th>Product</th>
            <th>站別</th>
            <th>Hold Reason</th>
            <th>數量</th>
            <th>Hold 時間</th>
            <th>Hold 人員</th>
            <th>Hold Comment</th>
            <th>Release 時間</th>
            <th>Release 人員</th>
            <th>Release Comment</th>
            <th>時長(hr)</th>
            <th>NCR</th>
            <th>Future Hold Comment</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="15" class="placeholder">Loading...</td>
          </tr>
          <tr v-else-if="errorMessage">
            <td colspan="15" class="placeholder">{{ errorMessage }}</td>
          </tr>
          <tr v-else-if="items.length === 0">
            <td colspan="15" class="placeholder">No data</td>
          </tr>
          <tr v-for="item in items" v-else :key="`${item.lotId}-${item.holdDate}-${item.releaseDate}`">
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

    <div class="pagination">
      <button type="button" :disabled="!canPrev" @click="emit('prev-page')">Prev</button>
      <span class="page-info">Page {{ pagination.page || 1 }} / {{ pagination.totalPages || 1 }}</span>
      <button type="button" :disabled="!canNext" @click="emit('next-page')">Next</button>
    </div>
  </section>

  <Teleport to="body">
    <div v-if="tip.visible" class="cell-tip" :style="{ left: tip.x + 'px', top: tip.y + 'px' }">
      {{ tip.text }}
    </div>
  </Teleport>
</template>
