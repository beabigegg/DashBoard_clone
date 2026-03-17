<script setup>
import { onMounted, ref, reactive, computed } from 'vue';
import { useRouter } from 'vue-router';
import { buildLaunchHref } from '../portal-shell/routeQuery.js';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { LineChart, BarChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, MarkLineComponent,
} from 'echarts/components';

use([CanvasRenderer, LineChart, BarChart, GridComponent, TooltipComponent, MarkLineComponent]);

const router = useRouter();

// ── 摘要卡片資料 ────────────────────────────────────────────────────────────
const summaryLoading = ref(true);
const summaryError = ref('');
const summaryData = ref(null);

// ── Drilldown 狀態 ──────────────────────────────────────────────────────────
const drilldown = reactive({
  sectionKey: null,
  itemIndex: -1,
  loading: false,
  error: '',
  items: [],
});

// ── 各區塊詳細資料 ──────────────────────────────────────────────────────────
const sections = ref([
  {
    key: 'yield',
    label: '良率異常',
    route: '/yield-alert-center',
    apiPath: '/api/analytics/yield-anomalies',
    algo: 'Z-score = (yield - rolling_avg) / rolling_std，以群組×封裝聚合，window=14天基線，看前日，僅抓良率下降，threshold=Z<-2.0',
    columns: [
      { key: 'date', label: '日期' },
      { key: 'workcenter_group', label: '站別群組' },
      { key: 'package', label: '封裝' },
      { key: 'yield_pct', label: '良率%' },
      { key: 'rolling_avg', label: '基線%' },
      { key: 'z_score', label: 'Z-score' },
      { key: 'scrap_qty', label: '報廢量' },
    ],
    items: [],
    loading: true,
    error: '',
    count: 0,
    expanded: false,
  },
  {
    key: 'reject',
    label: '報廢突增',
    route: '/reject-history',
    apiPath: '/api/analytics/reject-spikes',
    algo: 'Z-score = (當日報廢量 - 基線量) / 基線標準差，window=14天基線，看前日，僅抓量突增，threshold=Z>2.0',
    columns: [
      { key: 'date', label: '日期' },
      { key: 'workcenter_group', label: '站別群組' },
      { key: 'current_qty', label: '前日報廢量' },
      { key: 'baseline_qty', label: '基線量' },
      { key: 'z_score', label: 'Z-score' },
    ],
    items: [],
    loading: true,
    error: '',
    count: 0,
    expanded: false,
  },
  {
    key: 'hold',
    label: 'Hold 離群',
    route: '/hold-history',
    apiPath: '/api/analytics/hold-outliers',
    algo: '95th percentile of hold_hours（14天基線，僅品質異常類），僅看當日超過門檻的記錄',
    columns: [
      { key: 'hold_day', label: '日期' },
      { key: 'lot_id', label: 'Lot' },
      { key: 'hold_reason', label: '原因' },
      { key: 'workcenter', label: '工作站' },
      { key: 'hold_hours', label: '時數' },
      { key: 'percentile_threshold', label: '門檻' },
    ],
    items: [],
    loading: true,
    error: '',
    count: 0,
    expanded: false,
  },
  {
    key: 'equipment',
    label: '稼動偏離',
    route: '/resource-history',
    apiPath: '/api/analytics/equipment-deviation',
    algo: 'deviation = baseline_ou - current_ou，以群組×機型聚合，window=14天基線，看前日，threshold>15pp',
    columns: [
      { key: 'date', label: '日期' },
      { key: 'workcenter_group', label: '站別群組' },
      { key: 'resource_model', label: '機型' },
      { key: 'machine_count', label: '台數' },
      { key: 'current_ou_pct', label: '目前OU%' },
      { key: 'baseline_ou_pct', label: '基線OU%' },
      { key: 'deviation', label: '偏差' },
    ],
    items: [],
    loading: true,
    error: '',
    count: 0,
    expanded: false,
  },
]);

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(date) {
  const d = date instanceof Date ? date : new Date(date);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return formatDate(d);
}

function severityClass(severity) {
  if (severity === 'critical') return 'sev-critical';
  if (severity === 'warning') return 'sev-warning';
  return 'sev-ok';
}

function scrollToSection(key) {
  const el = document.getElementById(`section-${key}`);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function toggleSection(section) {
  section.expanded = !section.expanded;
}

// ── Drilldown ────────────────────────────────────────────────────────────────

function buildDrilldownUrl(sectionKey, item) {
  const base = '/api/analytics';
  switch (sectionKey) {
    case 'yield':
      return `${base}/yield-anomalies/drilldown?workcenter_group=${encodeURIComponent(item.workcenter_group)}&package=${encodeURIComponent(item.package)}`;
    case 'reject':
      return `${base}/reject-spikes/drilldown?workcenter_group=${encodeURIComponent(item.workcenter_group)}`;
    case 'hold':
      return `${base}/hold-outliers/drilldown?lot_id=${encodeURIComponent(item.lot_id)}&hold_day=${encodeURIComponent(item.hold_day)}`;
    case 'equipment':
      return `${base}/equipment-deviation/drilldown?workcenter_group=${encodeURIComponent(item.workcenter_group)}&resource_model=${encodeURIComponent(item.resource_model)}`;
    default:
      return null;
  }
}

function buildNavigateQuery(sectionKey, item) {
  const start = daysAgo(14);
  switch (sectionKey) {
    case 'yield':
      return {
        start_date: start,
        end_date: item.date,
        workcenter_groups: item.workcenter_group,
        packages: item.package,
      };
    case 'reject':
      return {
        start_date: start,
        end_date: item.date,
        workcenter_groups: item.workcenter_group,
      };
    case 'hold':
      return {
        start_date: item.hold_day,
        end_date: item.hold_day,
        hold_type: 'quality',
      };
    case 'equipment':
      return {
        start_date: start,
        end_date: item.date,
        workcenter_groups: item.workcenter_group,
        families: item.resource_model,
      };
    default:
      return {};
  }
}

function drilldownLabel(sectionKey, item) {
  switch (sectionKey) {
    case 'yield':
      return `${item.workcenter_group} / ${item.package}`;
    case 'reject':
      return item.workcenter_group;
    case 'hold':
      return `${item.lot_id} (${item.hold_day})`;
    case 'equipment':
      return `${item.workcenter_group} / ${item.resource_model}`;
    default:
      return '';
  }
}

const drilldownChartOption = computed(() => {
  const key = drilldown.sectionKey;
  const rows = drilldown.items;
  if (!rows || rows.length === 0 || key === 'hold') return null;

  const dates = rows.map((r) => r.date);
  const base = {
    tooltip: { trigger: 'axis' },
    grid: { left: 56, right: 24, top: 28, bottom: 28 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 11 } },
  };

  if (key === 'yield') {
    return {
      ...base,
      yAxis: { type: 'value', name: '%', min: 0, max: 100, axisLabel: { fontSize: 11 } },
      series: [
        {
          name: '良率%',
          type: 'line',
          data: rows.map((r) => r.yield_pct),
          smooth: true,
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2 },
          itemStyle: { color: '#4f46e5' },
        },
      ],
    };
  }

  if (key === 'reject') {
    return {
      ...base,
      yAxis: { type: 'value', name: '報廢量', axisLabel: { fontSize: 11 } },
      series: [
        {
          name: '報廢量',
          type: 'bar',
          data: rows.map((r) => r.reject_qty),
          itemStyle: { color: '#ef4444', borderRadius: [3, 3, 0, 0] },
        },
      ],
    };
  }

  if (key === 'equipment') {
    return {
      ...base,
      yAxis: { type: 'value', name: 'OU%', min: 0, max: 100, axisLabel: { fontSize: 11 } },
      series: [
        {
          name: 'OU%',
          type: 'line',
          data: rows.map((r) => r.avg_ou_pct),
          smooth: true,
          symbol: 'circle',
          symbolSize: 5,
          lineStyle: { width: 2 },
          areaStyle: { opacity: 0.1 },
          itemStyle: { color: '#0ea5e9' },
        },
      ],
    };
  }

  return null;
});

async function toggleDrilldown(sectionKey, idx, item) {
  // Hold 不支援 drilldown
  if (sectionKey === 'hold') return;

  // Toggle off if same item clicked
  if (drilldown.sectionKey === sectionKey && drilldown.itemIndex === idx) {
    drilldown.sectionKey = null;
    drilldown.itemIndex = -1;
    drilldown.items = [];
    return;
  }

  drilldown.sectionKey = sectionKey;
  drilldown.itemIndex = idx;
  drilldown.loading = true;
  drilldown.error = '';
  drilldown.items = [];

  const url = buildDrilldownUrl(sectionKey, item);
  if (!url) {
    drilldown.error = '不支援的類型';
    drilldown.loading = false;
    return;
  }

  try {
    const resp = await fetch(url);
    if (!resp.ok) {
      drilldown.error = `HTTP ${resp.status}`;
      return;
    }
    const payload = await resp.json();
    if (payload.success && Array.isArray(payload.data?.items)) {
      drilldown.items = payload.data.items;
    } else {
      drilldown.error = payload.error?.message || '無資料';
    }
  } catch (err) {
    drilldown.error = err?.message || '載入失敗';
  } finally {
    drilldown.loading = false;
  }
}

function navigateWithParams(section, item) {
  const query = buildNavigateQuery(section.key, item);
  const href = buildLaunchHref(section.route, query);
  router.push(href);
}

// ── Data loading ─────────────────────────────────────────────────────────────

async function loadSummary() {
  summaryLoading.value = true;
  summaryError.value = '';
  try {
    const resp = await fetch('/api/analytics/anomaly-summary');
    if (!resp.ok) {
      summaryError.value = `HTTP ${resp.status}`;
      return;
    }
    const payload = await resp.json();
    if (payload.success && payload.data) {
      summaryData.value = payload.data;
    } else {
      summaryError.value = payload.error?.message || '無法取得摘要';
    }
  } catch (err) {
    summaryError.value = err?.message || '摘要載入失敗';
  } finally {
    summaryLoading.value = false;
  }
}

async function loadSectionDetail(section) {
  section.loading = true;
  section.error = '';
  try {
    const resp = await fetch(section.apiPath);
    if (!resp.ok) {
      section.error = `HTTP ${resp.status}`;
      return;
    }
    const payload = await resp.json();
    if (payload.success && Array.isArray(payload.data?.items)) {
      section.items = payload.data.items;
      section.count = payload.data.count ?? section.items.length;
    } else {
      section.error = payload.error?.message || '無資料';
    }
  } catch (err) {
    section.error = err?.message || '載入失敗';
  } finally {
    section.loading = false;
  }
}

function applyDefaultExpand() {
  for (const section of sections.value) {
    section.expanded = section.count > 0;
  }
}

onMounted(async () => {
  await loadSummary();
  await Promise.all(sections.value.map((s) => loadSectionDetail(s)));
  applyDefaultExpand();
});
</script>

<template>
  <div class="anomaly-overview-page theme-anomaly-overview">
    <header class="ao-header">
      <h1>異常總覽</h1>
      <p>統整 4 種異常偵測器的結果，點擊列展開 14 天趨勢明細</p>
    </header>

    <!-- 摘要卡片 -->
    <section class="ao-summary-cards">
      <div v-if="summaryLoading" class="ao-loading-row">
        <span class="ao-spinner"></span> 載入摘要中...
      </div>
      <div v-else-if="summaryError" class="ao-error-row">摘要載入失敗：{{ summaryError }}</div>
      <template v-else-if="summaryData">
        <button
          v-for="section in sections"
          :key="section.key"
          class="ao-card"
          :class="severityClass(summaryData.breakdown[section.key]?.severity ?? 'ok')"
          type="button"
          @click="scrollToSection(section.key)"
        >
          <span class="ao-card-label">{{ section.label }}</span>
          <span class="ao-card-count">{{ summaryData.breakdown[section.key]?.count ?? '—' }}</span>
          <span class="ao-card-sev-dot"></span>
        </button>
      </template>
    </section>

    <!-- 4 個展開區塊 -->
    <section
      v-for="section in sections"
      :id="`section-${section.key}`"
      :key="section.key"
      class="ao-section"
    >
      <div class="ao-section-header" @click="toggleSection(section)">
        <div class="ao-section-header-left">
          <span class="ao-section-label">{{ section.label }}</span>
          <span class="ao-section-badge" :class="section.count > 5 ? 'badge-critical' : section.count > 0 ? 'badge-warning' : 'badge-ok'">
            {{ section.loading ? '…' : section.count }}
          </span>
          <span class="ao-toggle-icon">{{ section.expanded ? '▲' : '▼' }}</span>
        </div>
        <button
          class="ao-nav-link"
          type="button"
          @click.stop="navigateWithParams(section, section.items[0] || {})"
        >
          前往 {{ section.label }} →
        </button>
      </div>

      <div v-if="section.expanded" class="ao-section-body">
        <!-- 演算法說明卡片 -->
        <div class="ao-algo-card">
          <span class="ao-algo-label">偵測邏輯：</span>
          <span class="ao-algo-text">{{ section.algo }}</span>
        </div>

        <!-- 資料表格 -->
        <div v-if="section.loading" class="ao-loading-row">
          <span class="ao-spinner"></span> 載入中...
        </div>
        <div v-else-if="section.error" class="ao-error-row">{{ section.error }}</div>
        <div v-else-if="section.items.length === 0" class="ao-empty-row">無異常記錄</div>
        <div v-else class="ao-table-wrap">
          <table class="ao-table">
            <thead>
              <tr>
                <th v-for="col in section.columns" :key="col.key">{{ col.label }}</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(item, idx) in section.items" :key="idx">
                <tr
                  :class="section.key !== 'hold' ? 'ao-table-row' : ''"
                  :style="section.key !== 'hold' ? {} : { cursor: 'default' }"
                  @click="toggleDrilldown(section.key, idx, item)"
                >
                  <td
                    v-for="col in section.columns"
                    :key="col.key"
                    :class="{ 'ao-row-active': drilldown.sectionKey === section.key && drilldown.itemIndex === idx }"
                  >{{ item[col.key] ?? '—' }}</td>
                </tr>
                <!-- Drilldown panel (not for hold) -->
                <tr v-if="section.key !== 'hold' && drilldown.sectionKey === section.key && drilldown.itemIndex === idx" class="ao-drilldown-row">
                  <td :colspan="section.columns.length">
                    <div class="ao-drilldown-panel">
                      <div class="ao-drilldown-header">
                        <span class="ao-drilldown-title">14 天趨勢：{{ drilldownLabel(section.key, item) }}</span>
                        <button
                          class="ao-drilldown-nav"
                          type="button"
                          @click.stop="navigateWithParams(section, item)"
                        >
                          前往完整頁面 →
                        </button>
                      </div>
                      <div v-if="drilldown.loading" class="ao-loading-row">
                        <span class="ao-spinner"></span> 載入趨勢...
                      </div>
                      <div v-else-if="drilldown.error" class="ao-error-row">{{ drilldown.error }}</div>
                      <div v-else-if="drilldown.items.length === 0" class="ao-empty-row">無趨勢資料</div>
                      <div v-else-if="drilldownChartOption" class="ao-drilldown-chart">
                        <VChart :option="drilldownChartOption" :autoresize="{ throttle: 100 }" />
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>
