<script setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();

// ── 摘要卡片資料 ────────────────────────────────────────────────────────────
const summaryLoading = ref(true);
const summaryError = ref('');
const summaryData = ref(null);

// ── 各區塊詳細資料 ──────────────────────────────────────────────────────────
const sections = ref([
  {
    key: 'yield',
    label: '良率異常',
    route: '/yield-alert-center',
    apiPath: '/api/analytics/yield-anomalies',
    algo: 'Z-score = (yield - rolling_avg) / rolling_std，window=14天基線，僅看當日，threshold=|Z|>2.0',
    columns: [
      { key: 'date', label: '日期' },
      { key: 'line', label: '產線' },
      { key: 'package', label: '封裝' },
      { key: 'yield_pct', label: '良率%' },
      { key: 'z_score', label: 'Z-score' },
      { key: 'direction', label: '方向' },
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
    algo: 'pct_change = (current - baseline) / baseline × 100，window=14天基線，僅看當日，threshold>50%',
    columns: [
      { key: 'date', label: '日期' },
      { key: 'workcenter_group', label: '群組' },
      { key: 'current_rate', label: '目前率' },
      { key: 'baseline_rate', label: '基線率' },
      { key: 'pct_change', label: '變化%' },
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
    algo: '95th percentile of hold_hours（14天基線），僅看當日超過門檻的記錄',
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

function navigateTo(route) {
  router.push(route);
}

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
      <p>統整 4 種異常偵測器的結果，點擊區塊可查看詳情並導航至對應頁面</p>
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
          @click.stop="navigateTo(section.route)"
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
              <tr
                v-for="(item, idx) in section.items"
                :key="idx"
                class="ao-table-row"
                @click="navigateTo(section.route)"
              >
                <td v-for="col in section.columns" :key="col.key">{{ item[col.key] ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</template>
