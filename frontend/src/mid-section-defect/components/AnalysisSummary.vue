<script setup>
import { ref, watch } from 'vue';

const STORAGE_KEY = 'msd:summary-collapsed';

const props = defineProps({
  queryParams: {
    type: Object,
    default: () => ({}),
  },
  kpi: {
    type: Object,
    default: () => ({}),
  },
  totalAncestorCount: {
    type: Number,
    default: 0,
  },
  stationLabel: {
    type: String,
    default: '測試',
  },
});

const collapsed = ref(false);
const INPUT_TYPE_LABELS = Object.freeze({
  lot: 'LOT ID',
  lot_id: 'LOT ID',
  work_order: '工單',
  wafer_lot: 'WAFER LOT',
  serial_number: '成品流水號',
  gd_work_order: 'GD 工單',
  gd_lot_id: 'GD LOT ID',
});

// Restore from sessionStorage
try {
  const saved = sessionStorage.getItem(STORAGE_KEY);
  if (saved === 'true') collapsed.value = true;
} catch { /* unavailable */ }

watch(collapsed, (val) => {
  try {
    sessionStorage.setItem(STORAGE_KEY, val ? 'true' : 'false');
  } catch { /* quota */ }
});

function toggle() {
  collapsed.value = !collapsed.value;
}

function formatNumber(v) {
  if (v == null || v === 0) return '0';
  return Number(v).toLocaleString();
}

function formatInputType(value) {
  return INPUT_TYPE_LABELS[value] || value || 'LOT ID';
}
</script>

<template>
  <section class="summary-panel">
    <div class="summary-header" @click="toggle">
      <h3 class="summary-title">分析摘要</h3>
      <span class="summary-toggle">{{ collapsed ? '▸ 展開' : '▾ 收起' }}</span>
    </div>

    <div v-show="!collapsed" class="summary-body">
      <div class="summary-grid">
        <!-- Query context -->
        <div class="summary-block">
          <h4 class="block-title">查詢條件</h4>
          <ul class="block-list">
            <li>偵測站：{{ stationLabel }}</li>
            <template v-if="queryParams.queryMode === 'container'">
              <li>輸入方式：{{ formatInputType(queryParams.containerInputType) }}</li>
              <li v-if="queryParams.resolvedCount != null">解析數量：{{ queryParams.resolvedCount }} 筆</li>
              <li v-if="queryParams.notFoundCount > 0">未找到：{{ queryParams.notFoundCount }} 筆</li>
            </template>
            <template v-else>
              <li>日期範圍：{{ queryParams.startDate }} ~ {{ queryParams.endDate }}</li>
            </template>
            <li>報廢原因：{{ queryParams.lossReasons?.length ? queryParams.lossReasons.join(', ') : '全部' }}</li>
          </ul>
        </div>

        <!-- Data scope -->
        <div class="summary-block">
          <h4 class="block-title">數據範圍</h4>
          <ul class="block-list">
            <li>偵測站 LOT 總數：{{ formatNumber(kpi.lot_count) }}</li>
            <li>總投入：{{ formatNumber(kpi.total_input) }} pcs</li>
            <li>報廢 LOT 數：{{ formatNumber(kpi.defective_lot_count) }}</li>
            <li>報廢總數：{{ formatNumber(kpi.total_defect_qty) }} pcs</li>
            <li>血緣追溯涵蓋上游 LOT：{{ formatNumber(totalAncestorCount) }}</li>
          </ul>
        </div>

        <!-- Methodology -->
        <div class="summary-block summary-block-wide">
          <h4 class="block-title">歸因方法說明</h4>
          <p class="block-text">
            分析涵蓋所有經過偵測站的 LOT（包含無不良者），針對每筆 LOT 回溯血緣（split / merge chain）找到關聯的上游因子。
            歸因不良率 = 關聯 LOT 的報廢合計 / 關聯 LOT 的投入合計 × 100%。
            同一筆不良可歸因於多個上游因子（非互斥）。
            柏拉圖柱高 = 歸因不良數（含重疊），橙線 = 歸因不良率。
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.summary-panel {
  border: 1px solid var(--border-color, theme('colors.token.he5e7eb'));
  border-radius: 8px;
  background: var(--bg-secondary, theme('colors.token.hf9fafb'));
  margin-bottom: theme('spacing.token.p16');
}
.summary-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: theme('spacing.token.p10') theme('spacing.token.p16');
  cursor: pointer;
  user-select: none;
}
.summary-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary, theme('colors.token.h1f2937'));
}
.summary-toggle {
  font-size: 12px;
  color: var(--text-tertiary, theme('colors.token.h9ca3af'));
}
.summary-body {
  padding: 0 theme('spacing.token.p16') theme('spacing.token.p14');
}
.summary-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 24px;
}
.summary-block {
  min-width: 0;
}
.summary-block-wide {
  grid-column: 1 / -1;
}
.block-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary, theme('colors.token.h6b7280'));
  margin: 0 0 theme('spacing.token.p6');
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.block-list {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 13px;
  color: var(--text-primary, theme('colors.token.h374151'));
  line-height: 1.7;
}
.block-text {
  font-size: 12px;
  color: var(--text-secondary, theme('colors.token.h6b7280'));
  line-height: 1.6;
  margin: 0;
}
</style>
