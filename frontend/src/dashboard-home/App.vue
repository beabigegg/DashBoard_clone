<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api';
import { unwrapApiData } from '../core/unwrap-api-result';
import { splitHoldByType } from '../core/wip-derive';
import type { WipItem } from '../core/wip-derive';
import { useAutoRefresh } from '../shared-composables/useAutoRefresh';
import { createFreshnessGate } from '../shared-composables/useFreshnessGate';
import { useViewStaleness } from '../shared-composables/useViewStaleness';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import LoadingOverlay from '../shared-ui/components/LoadingOverlay.vue';

import EquipmentSection from './components/EquipmentSection.vue';
import HoldParetoSection from './components/HoldParetoSection.vue';
import WipSection from './components/WipSection.vue';

ensureMesApiAvailable();

const API_TIMEOUT = 60000;

interface WipStatusEntry {
  lots?: number;
  qtyPcs?: number;
}

interface WipSummary {
  totalLots?: number;
  totalQtyPcs?: number;
  byWipStatus?: Record<string, WipStatusEntry>;
}

interface EquipmentSummary {
  total_count?: number;
  by_status?: Record<string, number>;
  ou_pct?: number;
  availability_pct?: number;
}

interface EquipmentItem {
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  EQUIPMENTASSETSSTATUS: string;
}

const wipSummary = ref<WipSummary | null>(null);
const holdSplit = ref<{ quality: WipItem[]; nonQuality: WipItem[] }>({ quality: [], nonQuality: [] });
const equipmentSummary = ref<EquipmentSummary | null>(null);
const equipmentList = ref<EquipmentItem[]>([]);

const loading = reactive({
  initial: true,
  wipHold: false,
  equipment: false,
});

const wipHoldError = ref('');
const equipmentError = ref('');

// Two independently-triggered fetch groups (different refresh cadences below) —
// per-key staleness so a fast equipment refresh can't drop a slower in-flight
// WIP/Hold request, or vice versa.
const { nextRequestId, isStaleRequest } = useViewStaleness(['wipHold', 'equipment']);

async function loadWipAndHold(): Promise<void> {
  const rid = nextRequestId('wipHold');
  loading.wipHold = true;
  wipHoldError.value = '';

  try {
    const [summaryResult, holdResult] = await Promise.all([
      apiGet('/api/wip/overview/summary', { timeout: API_TIMEOUT, silent: true }),
      apiGet('/api/wip/overview/hold', { timeout: API_TIMEOUT, silent: true }),
    ]);
    if (isStaleRequest('wipHold', rid)) return;

    wipSummary.value = unwrapApiData(summaryResult, '載入 WIP 摘要失敗') as WipSummary;
    holdSplit.value = splitHoldByType(
      unwrapApiData(holdResult, '載入 Hold 資料失敗') as { items?: WipItem[] } | null | undefined
    );
  } catch (error) {
    if (isStaleRequest('wipHold', rid)) return;
    wipHoldError.value = (error as Error)?.message || 'WIP/Hold 資料載入失敗';
  } finally {
    if (!isStaleRequest('wipHold', rid)) loading.wipHold = false;
  }
}

async function loadEquipment(): Promise<void> {
  const rid = nextRequestId('equipment');
  loading.equipment = true;
  equipmentError.value = '';

  try {
    const [summaryResult, listResult] = await Promise.all([
      apiGet('/api/resource/status/summary', { params: { is_key: 1 }, timeout: API_TIMEOUT, silent: true }),
      apiGet('/api/resource/status', { params: { is_key: 1 }, timeout: API_TIMEOUT, silent: true }),
    ]);
    if (isStaleRequest('equipment', rid)) return;

    equipmentSummary.value = unwrapApiData(summaryResult, '載入設備摘要失敗') as EquipmentSummary;
    const list = unwrapApiData(listResult, '載入設備資料失敗');
    equipmentList.value = Array.isArray(list) ? (list as EquipmentItem[]) : [];
  } catch (error) {
    if (isStaleRequest('equipment', rid)) return;
    equipmentError.value = (error as Error)?.message || '設備資料載入失敗';
  } finally {
    if (!isStaleRequest('equipment', rid)) loading.equipment = false;
  }
}

// WIP + Hold overview pages share the same underlying WIP snapshot cache
// (~10 min write cadence) and both key off /health's cache.updated_at.
const wipHoldGate = createFreshnessGate(async () => {
  try {
    const health = await apiGet('/health', { timeout: 15000, retries: 0, silent: true });
    const data = health as { cache?: { updated_at?: string | null } } | null | undefined;
    return data?.cache?.updated_at ?? null;
  } catch {
    return null;
  }
});

// Equipment status is a separately-cached (~5 min sync worker) dataset from
// WIP — its own /health field (equipment_status_cache.updated_at).
const equipmentGate = createFreshnessGate(async () => {
  try {
    const health = await apiGet('/health', { timeout: 15000, retries: 0, silent: true });
    const data = health as { equipment_status_cache?: { updated_at?: string | null } } | null | undefined;
    return data?.equipment_status_cache?.updated_at ?? null;
  } catch {
    return null;
  }
});

useAutoRefresh({
  onRefresh: () => loadWipAndHold(),
  shouldRefresh: wipHoldGate.shouldRefresh,
  intervalMs: 60_000,
  autoStart: true,
});

useAutoRefresh({
  onRefresh: () => loadEquipment(),
  shouldRefresh: equipmentGate.shouldRefresh,
  intervalMs: 60_000,
  autoStart: true,
  refreshOnVisible: true,
});

async function initPage(): Promise<void> {
  await Promise.all([loadWipAndHold(), loadEquipment()]);
  loading.initial = false;
  void wipHoldGate.seed();
  void equipmentGate.seed();
}

onMounted(() => {
  void initPage();
});
</script>

<template>
  <div class="dashboard-home-page theme-dashboard-home" data-testid="dashboard-home-app">
    <div class="dashboard">
      <ErrorBanner :message="wipHoldError" @dismiss="wipHoldError = ''" />
      <ErrorBanner :message="equipmentError" @dismiss="equipmentError = ''" />

      <div class="dh-sections">
        <WipSection :summary="wipSummary" />
        <HoldParetoSection :quality="holdSplit.quality" :non-quality="holdSplit.nonQuality" />
        <EquipmentSection :summary="equipmentSummary" :equipment="equipmentList" />
      </div>
    </div>

    <LoadingOverlay v-if="loading.initial" tier="page" data-testid="loading-state" />
  </div>
</template>
