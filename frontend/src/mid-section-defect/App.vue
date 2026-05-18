<script setup lang="ts">
import { computed, reactive, ref } from 'vue';

import { apiGet, ensureMesApiAvailable } from '../core/api';
import { unwrapApiResult } from '../core/unwrap-api-result';
import { useFilterOrchestrator } from '../shared-composables/useFilterOrchestrator';
import { useTraceProgress } from '../shared-composables/useTraceProgress';
// @ts-expect-error TraceProgressBar.vue is not yet migrated to lang="ts" (Phase 3 in-progress)
import TraceProgressBar from '../shared-composables/TraceProgressBar.vue';

import EmptyState from '../shared-ui/components/EmptyState.vue';
import ErrorBanner from '../shared-ui/components/ErrorBanner.vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';
import PageHeader from '../shared-ui/components/PageHeader.vue';

// Components below are kept as plain SFCs (no lang="ts") per migration scope — Phase 3 in-progress
// @ts-expect-error AnalysisSummary.vue not yet migrated to lang="ts"
import AnalysisSummary from './components/AnalysisSummary.vue';
// @ts-expect-error DetailTable.vue not yet migrated to lang="ts"
import DetailTable from './components/DetailTable.vue';
// @ts-expect-error FilterBar.vue not yet migrated to lang="ts"
import FilterBar from './components/FilterBar.vue';
// @ts-expect-error KpiCards.vue not yet migrated to lang="ts"
import KpiCards from './components/KpiCards.vue';
// @ts-expect-error ParetoChart.vue not yet migrated to lang="ts"
import ParetoChart from './components/ParetoChart.vue';
// @ts-expect-error SuspectContextPanel.vue not yet migrated to lang="ts"
import SuspectContextPanel from './components/SuspectContextPanel.vue';
// @ts-expect-error TrendChart.vue not yet migrated to lang="ts"
import TrendChart from './components/TrendChart.vue';

ensureMesApiAvailable();

// ---------------------------------------------------------------------------
// Local interfaces for API response shapes used in this app
// ---------------------------------------------------------------------------

interface StationOption {
  name: string;
  label?: string;
}

interface AttributionRecord {
  MATERIAL_KEY: string;
  INPUT_QTY: number;
  DEFECT_QTY: number;
  DETECTION_LOT_COUNT: number;
  EQUIPMENT_NAME?: string;
  EQUIPMENT_ID?: string;
  WORKCENTER_GROUP?: string;
  RESOURCEFAMILYNAME?: string;
  MATERIAL_PART_NAME?: string;
}

interface ChartItem {
  name: string;
  input_qty: number;
  defect_qty: number;
  defect_rate: number;
  lot_count: number;
  cumulative_pct?: number;
}

interface ChartsByKey {
  by_machine?: ChartItem[];
  by_material?: ChartItem[];
  by_wafer_root?: ChartItem[];
  by_workflow?: ChartItem[];
  by_loss_reason?: ChartItem[];
  by_detection_machine?: ChartItem[];
  by_downstream_station?: ChartItem[];
  by_downstream_loss_reason?: ChartItem[];
  by_downstream_machine?: ChartItem[];
}

interface MsdAnalysisData {
  kpi: Record<string, unknown>;
  charts: ChartsByKey;
  attribution?: AttributionRecord[];
  materials_attribution?: AttributionRecord[];
  daily_trend: unknown[];
  genealogy_status: string;
  detail_total_count: number;
  total_ancestor_count?: number;
}

interface DetailPagination {
  page: number;
  page_size: number;
  total_count: number;
  total_pages: number;
}

interface CommittedFilters {
  startDate: string;
  endDate: string;
  lossReasons: string[];
  station: string;
  direction: string;
  queryMode?: string;
  containerInputType?: string;
  containerValues?: string[];
}

interface ResolutionInfo {
  resolved_count: number;
  not_found: string[];
}

interface SessionCache {
  ts: number;
  committedFilters: CommittedFilters;
  filters: {
    startDate: string;
    endDate: string;
    lossReasons: string[];
    station: string;
    direction: string;
  };
  analysisData: MsdAnalysisData;
  detailData: unknown[];
  detailPagination: DetailPagination;
  availableLossReasons: string[];
  queryMode: string;
  containerInputType: string;
  containerInput: string;
  resolutionInfo: ResolutionInfo | null;
}

const API_TIMEOUT = 360000;
const PAGE_SIZE = 20;
const SESSION_CACHE_KEY = 'msd:cache';
const SESSION_CACHE_TTL = 5 * 60 * 1000; // 5 min, matches backend Redis TTL
const CHART_TOP_N = 10;

function buildMaterialChartFromAttribution(records: AttributionRecord[]): ChartItem[] {
  if (!records || records.length === 0) return [];
  const sorted = [...records].sort((a, b) => b.DEFECT_QTY - a.DEFECT_QTY);
  const items: ChartItem[] = [];
  const other = { input_qty: 0, defect_qty: 0, lot_count: 0 };
  for (let i = 0; i < sorted.length; i++) {
    const rec = sorted[i];
    if (i < CHART_TOP_N) {
      const rate = rec.INPUT_QTY > 0 ? Math.round((rec.DEFECT_QTY / rec.INPUT_QTY) * 1e6) / 1e4 : 0;
      items.push({ name: rec.MATERIAL_KEY, input_qty: rec.INPUT_QTY, defect_qty: rec.DEFECT_QTY, defect_rate: rate, lot_count: rec.DETECTION_LOT_COUNT });
    } else {
      other.input_qty += rec.INPUT_QTY;
      other.defect_qty += rec.DEFECT_QTY;
      other.lot_count += rec.DETECTION_LOT_COUNT;
    }
  }
  if (other.defect_qty > 0 || other.input_qty > 0) {
    const rate = other.input_qty > 0 ? Math.round((other.defect_qty / other.input_qty) * 1e6) / 1e4 : 0;
    items.push({ name: '其他', ...other, defect_rate: rate });
  }
  const totalDefects = items.reduce((s, d) => s + d.defect_qty, 0);
  let cumsum = 0;
  for (const item of items) {
    cumsum += item.defect_qty;
    item.cumulative_pct = totalDefects > 0 ? Math.round((cumsum / totalDefects) * 1e4) / 100 : 0;
  }
  return items;
}

function buildMachineChartFromAttribution(records: AttributionRecord[]): ChartItem[] {
  if (!records || records.length === 0) return [];
  const agg: Record<string, { input_qty: number; defect_qty: number; lot_count: number }> = {};
  for (const rec of records) {
    const key = rec.EQUIPMENT_NAME || '(未知)';
    if (!agg[key]) agg[key] = { input_qty: 0, defect_qty: 0, lot_count: 0 };
    agg[key].input_qty += rec.INPUT_QTY;
    agg[key].defect_qty += rec.DEFECT_QTY;
    agg[key].lot_count += rec.DETECTION_LOT_COUNT;
  }
  const sorted = Object.entries(agg).sort((a, b) => b[1].defect_qty - a[1].defect_qty);
  const items: ChartItem[] = [];
  const other = { input_qty: 0, defect_qty: 0, lot_count: 0 };
  for (let i = 0; i < sorted.length; i++) {
    const [name, data] = sorted[i];
    if (i < CHART_TOP_N) {
      const rate = data.input_qty > 0 ? Math.round((data.defect_qty / data.input_qty) * 1e6) / 1e4 : 0;
      items.push({ name, input_qty: data.input_qty, defect_qty: data.defect_qty, defect_rate: rate, lot_count: data.lot_count });
    } else {
      other.input_qty += data.input_qty;
      other.defect_qty += data.defect_qty;
      other.lot_count += data.lot_count;
    }
  }
  if (other.defect_qty > 0 || other.input_qty > 0) {
    const rate = other.input_qty > 0 ? Math.round((other.defect_qty / other.input_qty) * 1e6) / 1e4 : 0;
    items.push({ name: '其他', ...other, defect_rate: rate });
  }
  const totalDefects = items.reduce((s, d) => s + d.defect_qty, 0);
  let cumsum = 0;
  for (const item of items) {
    cumsum += item.defect_qty;
    item.cumulative_pct = totalDefects > 0 ? Math.round((cumsum / totalDefects) * 1e4) / 100 : 0;
  }
  return items;
}

const stationOptions = ref<StationOption[]>([]);
(async () => {
  try {
    const result = await apiGet<StationOption[]>('/api/mid-section-defect/station-options');
    if (result?.success && Array.isArray(result.data)) {
      stationOptions.value = result.data;
    }
  } catch { /* non-blocking */ }
})();
const stationLabelMap = computed((): Record<string, string> => {
  const m: Record<string, string> = {};
  for (const opt of stationOptions.value) {
    m[opt.name] = opt.label || opt.name;
  }
  return m;
});

const filters = reactive<{
  startDate: string;
  endDate: string;
  lossReasons: string[];
  station: string;
  direction: string;
}>({
  startDate: '',
  endDate: '',
  lossReasons: [],
  station: '測試',
  direction: 'backward',
});
const committedFilters = ref<CommittedFilters>({
  startDate: '',
  endDate: '',
  lossReasons: [],
  station: '測試',
  direction: 'backward',
});

const queryMode = ref<string>('date_range');
const containerInputType = ref<string>('lot');
const containerInput = ref<string>('');
const resolutionInfo = ref<ResolutionInfo | null>(null);

const availableLossReasons = ref<string[]>([]);
const trace = useTraceProgress({ profile: 'mid_section_defect' });

// Canonical trace_query_id from spool-hit or async job result.
// Passed to detail/export so the backend can serve from spool instead of Oracle.
const currentTraceQueryId = ref<string | null>(null);

const analysisData = ref<MsdAnalysisData>({
  kpi: {},
  charts: {},
  daily_trend: [],
  genealogy_status: 'ready',
  detail_total_count: 0,
});

const detailData = ref<unknown[]>([]);
const detailPagination = ref<DetailPagination>({
  page: 1,
  page_size: PAGE_SIZE,
  total_count: 0,
  total_pages: 1,
});
const detailLoading = ref<boolean>(false);

const loading = reactive<{ querying: boolean }>({
  querying: false,
});

const hasQueried = ref<boolean>(false);
const queryError = ref<string>('');
const restoredFromCache = ref<boolean>(false);

// --- Cascading chart filters: station -> spec prune via useFilterOrchestrator ---
const {
  committed: upstreamChartFilters,
  updateField: updateUpstreamField,
} = useFilterOrchestrator({
  fields: {
    station: { trigger: 'immediate', initial: [] },
    spec:    { trigger: 'immediate', initial: [] },
  },
  dependencies: [
    { when: 'station', then: ['spec'], action: 'clear' },
  ],
});
const upstreamStationFilter = computed({
  get: () => (upstreamChartFilters.station as unknown as string[]),
  set: (v: string[]) => updateUpstreamField('station', v),
});
const upstreamSpecFilter = computed({
  get: () => (upstreamChartFilters.spec as unknown as string[]),
  set: (v: string[]) => updateUpstreamField('spec', v),
});
const upstreamStationOptions = computed(() => {
  const attribution = analysisData.value?.attribution;
  if (!Array.isArray(attribution) || attribution.length === 0) return [];
  const seen = new Set();
  const options = [];
  for (const rec of attribution) {
    const group = rec.WORKCENTER_GROUP;
    if (group && !seen.has(group)) {
      seen.add(group);
      options.push({ value: group, label: stationLabelMap.value[group] || group });
    }
  }
  return options.sort((a, b) => a.label.localeCompare(b.label, 'zh-TW'));
});
const upstreamSpecOptions = computed(() => {
  const attribution = analysisData.value?.attribution;
  if (!Array.isArray(attribution) || attribution.length === 0) return [];
  // Apply station filter first so spec options are contextual
  const base = upstreamStationFilter.value.length > 0
    ? attribution.filter(rec => upstreamStationFilter.value.includes(rec.WORKCENTER_GROUP ?? ''))
    : attribution;
  const seen = new Set();
  const options = [];
  for (const rec of base) {
    const family = rec.RESOURCEFAMILYNAME;
    if (family && family !== '(未知)' && !seen.has(family)) {
      seen.add(family);
      options.push(family);
    }
  }
  return options.sort((a, b) => a.localeCompare(b, 'zh-TW'));
});
const filteredByMachineData = computed(() => {
  const attribution = analysisData.value?.attribution;
  const hasFilter = upstreamStationFilter.value.length > 0 || upstreamSpecFilter.value.length > 0;
  if (!hasFilter || !Array.isArray(attribution) || attribution.length === 0) {
    return analysisData.value?.charts?.by_machine ?? [];
  }
  const filtered = attribution.filter(rec => {
    if (upstreamStationFilter.value.length > 0 && !upstreamStationFilter.value.includes(rec.WORKCENTER_GROUP ?? '')) return false;
    if (upstreamSpecFilter.value.length > 0 && !upstreamSpecFilter.value.includes(rec.RESOURCEFAMILYNAME ?? '')) return false;
    return true;
  });
  return filtered.length > 0 ? buildMachineChartFromAttribution(filtered) : [];
});

// --- Material type filter for raw material chart ---
const {
  committed: materialChartFilters,
  updateField: updateMaterialField,
} = useFilterOrchestrator({
  fields: {
    materialType: { trigger: 'immediate', initial: [] },
  },
});
const materialTypeFilter = computed({
  get: () => (materialChartFilters.materialType as unknown as string[]),
  set: (v: string[]) => updateMaterialField('materialType', v),
});
const materialTypeOptions = computed(() => {
  const materials = analysisData.value?.materials_attribution;
  if (!Array.isArray(materials) || materials.length === 0) return [];
  const seen = new Set();
  const options = [];
  for (const rec of materials) {
    const part = rec.MATERIAL_PART_NAME;
    if (part && !seen.has(part)) {
      seen.add(part);
      options.push(part);
    }
  }
  return options.sort((a, b) => a.localeCompare(b, 'zh-TW'));
});
const filteredByMaterialData = computed(() => {
  const materials = analysisData.value?.materials_attribution;
  const hasFilter = materialTypeFilter.value.length > 0;
  if (!hasFilter || !Array.isArray(materials) || materials.length === 0) {
    return analysisData.value?.charts?.by_material ?? [];
  }
  const filtered = materials.filter(rec => materialTypeFilter.value.includes(rec.MATERIAL_PART_NAME ?? ''));
  return filtered.length > 0 ? buildMaterialChartFromAttribution(filtered) : [];
});

const suspectMachineNames = computed(() => {
  const data = filteredByMachineData.value;
  if (!Array.isArray(data)) return [];
  return data.filter((d) => d.name && d.name !== '其他').map((d) => d.name);
});

const isForward = computed(() => committedFilters.value.direction === 'forward');
const committedStation = computed(() => {
  const key = committedFilters.value.station || '測試';
  return stationLabelMap.value[key] || key;
});

const headerSubtitle = computed(() => {
  const station = committedStation.value;
  if (isForward.value) {
    return `${station}站不良批次 → 追蹤倖存批次下游表現`;
  }
  return `${station}站不良 → 回溯上游機台歸因`;
});

const hasTraceError = computed(() => (
  Boolean(trace.stage_errors.seed)
  || Boolean(trace.stage_errors.lineage)
  || Boolean(trace.stage_errors.events)
));
const showTraceProgress = computed(() => (
  loading.querying
  || trace.completed_stages.value.length > 0
  || hasTraceError.value
));
interface EventsStageResult {
  aggregation?: Record<string, unknown>;
  quality_meta?: { status?: string };
  trace_query_id?: string;
}
interface LineageStageResult {
  total_ancestor_count?: number;
}
interface SeedStageResult {
  seed_count?: number;
  not_found?: string[];
}
const eventsAggregation = computed(() => (trace.stage_results.events as unknown as EventsStageResult | null)?.aggregation || null);
const eventsQualityMeta = computed(() => (trace.stage_results.events as unknown as EventsStageResult | null)?.quality_meta || null);
const hasCompletenessWarning = computed(() => {
  if (!hasQueried.value || loading.querying) return false;
  const status = String(eventsQualityMeta.value?.status || '').toLowerCase();
  return Boolean(status) && status !== 'complete';
});
const completenessWarningText = computed(() => {
  const status = String(eventsQualityMeta.value?.status || '').toLowerCase();
  if (status === 'partial') return '部分事件資料尚未完整擷取，分析結果可能不完整。';
  if (status === 'truncated') return '事件資料已截斷，超出查詢限制，分析結果可能不完整。';
  if (status === 'failed') return '部分事件域擷取失敗，分析結果可能不完整。';
  return '';
});
const showAnalysisSkeleton = computed(() => hasQueried.value && loading.querying && !eventsAggregation.value);
const showAnalysisCharts = computed(() => hasQueried.value && (Boolean(eventsAggregation.value) || restoredFromCache.value));

const skeletonChartCount = computed(() => (isForward.value ? 4 : 6));

const totalAncestorCount = computed(() => (trace.stage_results.lineage as unknown as LineageStageResult | null)?.total_ancestor_count || analysisData.value?.total_ancestor_count || 0);

const summaryQueryParams = computed(() => {
  const snap = committedFilters.value;
  const params: {
    queryMode: string;
    startDate: string;
    endDate: string;
    lossReasons: string[];
    containerInputType?: string;
    resolvedCount?: number;
    notFoundCount?: number;
  } = {
    queryMode: snap.queryMode || 'date_range',
    startDate: snap.startDate,
    endDate: snap.endDate,
    lossReasons: snap.lossReasons || [],
  };
  if (snap.queryMode === 'container') {
    params.containerInputType = snap.containerInputType || 'lot';
    params.resolvedCount = resolutionInfo.value?.resolved_count || 0;
    params.notFoundCount = resolutionInfo.value?.not_found?.length || 0;
  }
  return params;
});

function emptyAnalysisData() {
  return {
    kpi: {},
    charts: {},
    daily_trend: [],
    genealogy_status: 'ready',
    detail_total_count: 0,
  };
}

function setDefaultDates() {
  const today = new Date();
  const endDate = new Date(today);
  endDate.setDate(endDate.getDate() - 1);

  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 6);

  filters.startDate = toDateString(startDate);
  filters.endDate = toDateString(endDate);
}

function toDateString(value: Date): string {
  return value.toISOString().slice(0, 10);
}

// unwrapApiResult imported from ../core/unwrap-api-result.js

function buildFilterParams(): Record<string, unknown> {
  const snapshot = committedFilters.value;
  const params: Record<string, unknown> = {
    station: snapshot.station,
    direction: snapshot.direction,
  };
  if (snapshot.lossReasons.length) {
    params.loss_reasons = snapshot.lossReasons;
  }
  if (snapshot.queryMode === 'container') {
    params.mode = 'container';
    params.resolve_type = snapshot.containerInputType === 'lot' ? 'lot_id' : snapshot.containerInputType;
    params.values = snapshot.containerValues;
  } else {
    params.start_date = snapshot.startDate;
    params.end_date = snapshot.endDate;
  }
  return params;
}

function buildDetailParams(): Record<string, unknown> {
  const snapshot = committedFilters.value;
  const params: Record<string, unknown> = {
    start_date: snapshot.startDate,
    end_date: snapshot.endDate,
    station: snapshot.station,
    direction: snapshot.direction,
  };
  if (snapshot.lossReasons.length) {
    params.loss_reasons = snapshot.lossReasons.join(',');
  }
  // Pass canonical trace_query_id when available so backend serves from spool.
  if (currentTraceQueryId.value) {
    params.trace_query_id = currentTraceQueryId.value;
  }
  return params;
}

function parseContainerValues() {
  return containerInput.value
    .split(/[\n,;]+/)
    .map((v) => v.trim().replace(/\*/g, '%'))
    .filter(Boolean);
}

function snapshotFilters() {
  committedFilters.value = {
    startDate: filters.startDate,
    endDate: filters.endDate,
    lossReasons: [...filters.lossReasons],
    station: filters.station,
    direction: filters.direction,
    queryMode: queryMode.value,
    containerInputType: containerInputType.value,
    containerValues: parseContainerValues(),
  };
}

function firstStageErrorMessage() {
  const stageError = trace.stage_errors.seed || trace.stage_errors.lineage || trace.stage_errors.events;
  return stageError?.message || '';
}

async function loadLossReasons() {
  try {
    const result = await apiGet('/api/mid-section-defect/loss-reasons');
    const unwrapped = unwrapApiResult(result, '載入不良原因失敗') as { data?: { loss_reasons?: string[] } } | null;
    availableLossReasons.value = unwrapped?.data?.loss_reasons || [];
  } catch {
    // Non-blocking, dropdown remains empty.
  }
}

async function loadDetail(page = 1, signal: AbortSignal | null = null): Promise<void> {
  detailLoading.value = true;
  try {
    const params = {
      ...buildDetailParams(),
      page,
      page_size: PAGE_SIZE,
    };
    const result = await apiGet('/api/mid-section-defect/analysis/detail', {
      params,
      timeout: API_TIMEOUT,
      signal: signal ?? undefined,
    });
    const unwrapped = unwrapApiResult(result, '載入明細失敗') as { data?: { detail?: unknown[]; pagination?: DetailPagination } } | null;
    detailData.value = unwrapped?.data?.detail || [];
    detailPagination.value = unwrapped?.data?.pagination || {
      page: 1,
      page_size: PAGE_SIZE,
      total_count: 0,
      total_pages: 1,
    };
  } catch (err) {
    if ((err as { name?: string })?.name === 'AbortError') {
      return;
    }
    console.error('Detail load failed:', (err as Error).message);
    detailData.value = [];
  } finally {
    detailLoading.value = false;
  }
}

async function loadAnalysis() {
  queryError.value = '';
  restoredFromCache.value = false;
  resolutionInfo.value = null;
  currentTraceQueryId.value = null;
  updateUpstreamField('station', []);
  updateUpstreamField('spec', []);
  updateMaterialField('materialType', []);
  trace.abort();
  trace.reset();
  loading.querying = true;
  hasQueried.value = true;
  analysisData.value = emptyAnalysisData();

  const isContainerMode = committedFilters.value.queryMode === 'container';

  try {
    const params = buildFilterParams();
    await trace.execute(params);

    // Extract resolution info for container mode
    if (isContainerMode && trace.stage_results.seed) {
      const seed = trace.stage_results.seed as unknown as SeedStageResult;
      resolutionInfo.value = {
        resolved_count: seed.seed_count || 0,
        not_found: seed.not_found || [],
      };
    }

    if (eventsAggregation.value) {
      const lineage = trace.stage_results.lineage as unknown as LineageStageResult | null;
      analysisData.value = {
        ...analysisData.value,
        ...eventsAggregation.value,
        total_ancestor_count: lineage?.total_ancestor_count || 0,
      };
    }

    // Capture canonical trace_query_id for spool-backed detail/export calls.
    const eventsResult = trace.stage_results.events as unknown as EventsStageResult | null;
    if (eventsResult?.trace_query_id) {
      currentTraceQueryId.value = eventsResult.trace_query_id;
    }

    const stageError = firstStageErrorMessage();
    if (stageError) {
      queryError.value = stageError;
    }

    if (!stageError || trace.completed_stages.value.includes('events')) {
      await loadDetail(1, createAbortSignal('msd-detail'));
      saveSession();
    }

  } catch (err) {
    if ((err as { name?: string })?.name === 'AbortError') {
      return;
    }
    queryError.value = (err as Error).message || '查詢失敗，請稍後再試';
  } finally {
    loading.querying = false;
  }
}

function handleUpdateFilters(updated: Partial<typeof filters>): void {
  Object.assign(filters, updated);
}

function handleQuery() {
  snapshotFilters();
  void loadAnalysis();
}

function prevPage() {
  if (detailPagination.value.page <= 1) return;
  void loadDetail(detailPagination.value.page - 1, createAbortSignal('msd-detail'));
}

function nextPage() {
  if (detailPagination.value.page >= detailPagination.value.total_pages) return;
  void loadDetail(detailPagination.value.page + 1, createAbortSignal('msd-detail'));
}

function exportCsv() {
  const snapshot = committedFilters.value;
  const params = new URLSearchParams({
    start_date: snapshot.startDate,
    end_date: snapshot.endDate,
    station: snapshot.station,
    direction: snapshot.direction,
  });
  if (snapshot.lossReasons.length) {
    params.set('loss_reasons', snapshot.lossReasons.join(','));
  }
  // Pass canonical trace_query_id when available so backend streams from spool.
  if (currentTraceQueryId.value) {
    params.set('trace_query_id', currentTraceQueryId.value);
  }

  const link = document.createElement('a');
  link.href = `/api/mid-section-defect/export?${params.toString()}`;
  const datePart = snapshot.queryMode === 'container'
    ? (currentTraceQueryId.value || snapshot.containerInputType || 'container')
    : `${snapshot.startDate}_to_${snapshot.endDate}`;
  link.download = `mid_section_defect_${snapshot.station}_${snapshot.direction}_${datePart}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// Suspect context panel state
const suspectPanelMachine = ref<AttributionRecord | null>(null);

function handleMachineBarClick({ name, dataIndex }: { name: string; dataIndex: number }): void {
  if (!name || name === '其他') return;
  const attribution = analysisData.value?.attribution;
  if (!Array.isArray(attribution)) return;
  const match = attribution.find(
    (rec) => rec.EQUIPMENT_NAME === name,
  );
  if (match) {
    suspectPanelMachine.value = suspectPanelMachine.value?.EQUIPMENT_NAME === name ? null : match;
  }
}

const _abortControllers = new Map<string, AbortController>();
function createAbortSignal(key = 'default'): AbortSignal {
  const prev = _abortControllers.get(key);
  if (prev) prev.abort();
  const ctrl = new AbortController();
  _abortControllers.set(key, ctrl);
  return ctrl.signal;
}

function saveSession() {
  try {
    sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify({
      ts: Date.now(),
      committedFilters: committedFilters.value,
      filters: { ...filters },
      analysisData: analysisData.value,
      detailData: detailData.value,
      detailPagination: detailPagination.value,
      availableLossReasons: availableLossReasons.value,
      queryMode: queryMode.value,
      containerInputType: containerInputType.value,
      containerInput: containerInput.value,
      resolutionInfo: resolutionInfo.value,
    }));
  } catch { /* quota exceeded or unavailable */ }
}

function restoreSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_CACHE_KEY);
    if (!raw) return false;
    const data = JSON.parse(raw);
    if (Date.now() - data.ts > SESSION_CACHE_TTL) {
      sessionStorage.removeItem(SESSION_CACHE_KEY);
      return false;
    }
    Object.assign(filters, data.filters);
    committedFilters.value = data.committedFilters;
    analysisData.value = data.analysisData;
    detailData.value = data.detailData || [];
    detailPagination.value = data.detailPagination || { page: 1, page_size: PAGE_SIZE, total_count: 0, total_pages: 1 };
    availableLossReasons.value = data.availableLossReasons || [];
    queryMode.value = data.queryMode || 'date_range';
    containerInputType.value = data.containerInputType || 'lot';
    containerInput.value = data.containerInput || '';
    resolutionInfo.value = data.resolutionInfo || null;
    hasQueried.value = true;
    restoredFromCache.value = true;
    return true;
  } catch {
    return false;
  }
}

function initPage() {
  if (restoreSession()) return;
  setDefaultDates();
  snapshotFilters();
  void loadLossReasons();
}

void initPage();
</script>

<template>
  <div class="dashboard theme-mid-section-defect">
    <PageHeader
      title="製程不良追溯分析"
      :show-refresh="false"
    />

    <FilterBar
      :filters="filters"
      :loading="loading.querying"
      :available-loss-reasons="availableLossReasons"
      :station-options="stationOptions"
      :query-mode="queryMode"
      :container-input-type="containerInputType"
      :container-input="containerInput"
      :resolution-info="resolutionInfo"
      @update-filters="handleUpdateFilters"
      @query="handleQuery"
      @update:query-mode="queryMode = $event"
      @update:container-input-type="containerInputType = $event"
      @update:container-input="containerInput = $event"
    />

    <TraceProgressBar
      v-if="showTraceProgress"
      :current_stage="trace.current_stage.value"
      :completed_stages="trace.completed_stages.value"
      :stage_errors="trace.stage_errors"
    />

    <ErrorBanner :message="queryError" :dismissible="false" />

    <template v-if="hasQueried">
      <div v-if="analysisData.genealogy_status === 'error'" class="warning-banner">
        追溯分析未完成（genealogy 查詢失敗），圖表僅顯示偵測站數據。
      </div>
      <div v-if="hasCompletenessWarning" class="warning-banner">
        {{ completenessWarningText }}
      </div>

      <div v-if="showAnalysisSkeleton" class="trace-skeleton-section">
        <div class="trace-skeleton-kpi-grid">
          <div v-for="index in 6" :key="`kpi-${index}`" class="trace-skeleton-card trace-skeleton-pulse"></div>
        </div>
        <div class="trace-skeleton-chart-grid">
          <div v-for="index in skeletonChartCount" :key="`chart-${index}`" class="trace-skeleton-chart trace-skeleton-pulse"></div>
          <div class="trace-skeleton-chart trace-skeleton-trend trace-skeleton-pulse"></div>
        </div>
      </div>

      <transition name="trace-fade">
        <div v-if="showAnalysisCharts">
          <AnalysisSummary
            v-if="!isForward"
            :query-params="summaryQueryParams"
            :kpi="analysisData.kpi"
            :total-ancestor-count="totalAncestorCount"
            :station-label="committedStation"
          />

          <KpiCards
            :kpi="analysisData.kpi"
            :loading="false"
            :direction="committedFilters.direction"
            :station-label="committedStation"
          />

          <div class="charts-section">
            <template v-if="!isForward">
              <div class="charts-row">
                <div class="chart-with-panel">
                  <ParetoChart title="依上游機台歸因" :data="filteredByMachineData" enable-click @bar-click="handleMachineBarClick">
                    <template #header-extra>
                      <div class="chart-inline-filters">
                        <MultiSelect
                          v-if="upstreamStationOptions.length > 1"
                          :model-value="upstreamStationFilter"
                          :options="upstreamStationOptions"
                          placeholder="全部站點"
                          @update:model-value="upstreamStationFilter = $event"
                        />
                        <MultiSelect
                          v-if="upstreamSpecOptions.length > 1"
                          :model-value="upstreamSpecFilter"
                          :options="upstreamSpecOptions"
                          placeholder="全部型號"
                          @update:model-value="upstreamSpecFilter = $event"
                        />
                      </div>
                    </template>
                  </ParetoChart>
                  <SuspectContextPanel
                    :machine="suspectPanelMachine"
                    @close="suspectPanelMachine = null"
                  />
                </div>
                <ParetoChart title="依原物料歸因" :data="filteredByMaterialData">
                  <template #header-extra>
                    <div class="chart-inline-filters">
                      <MultiSelect
                        v-if="materialTypeOptions.length > 1"
                        :model-value="materialTypeFilter"
                        :options="materialTypeOptions"
                        placeholder="全部原物料"
                        @update:model-value="materialTypeFilter = $event"
                      />
                    </div>
                  </template>
                </ParetoChart>
              </div>
              <div class="charts-row">
                <ParetoChart title="依源頭批次歸因" :data="analysisData.charts?.by_wafer_root" />
                <ParetoChart title="依Workflow歸因" :data="analysisData.charts?.by_workflow" />
              </div>
              <div class="charts-row">
                <ParetoChart title="依不良原因" :data="analysisData.charts?.by_loss_reason" />
                <ParetoChart title="依偵測機台" :data="analysisData.charts?.by_detection_machine" />
              </div>
            </template>
            <template v-else>
              <div class="charts-row">
                <ParetoChart title="依下游站點" :data="analysisData.charts?.by_downstream_station" />
                <ParetoChart title="依下游不良原因" :data="analysisData.charts?.by_downstream_loss_reason" />
              </div>
              <div class="charts-row">
                <ParetoChart title="依下游機台" :data="analysisData.charts?.by_downstream_machine" />
                <ParetoChart title="依偵測機台" :data="analysisData.charts?.by_detection_machine" />
              </div>
            </template>
            <div v-if="committedFilters.queryMode !== 'container'" class="charts-row charts-row-full">
              <TrendChart :data="analysisData.daily_trend" />
            </div>
          </div>
        </div>
      </transition>

      <DetailTable
        :data="detailData"
        :loading="detailLoading"
        :pagination="detailPagination"
        :direction="committedFilters.direction"
        :suspect-machines="suspectMachineNames"
        @export-csv="exportCsv"
        @prev-page="prevPage"
        @next-page="nextPage"
      />
    </template>

    <EmptyState v-else-if="!loading.querying" type="no-data" />
  </div>
</template>
