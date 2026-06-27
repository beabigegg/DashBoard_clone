<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue';
import MultiSelect from '../shared-ui/components/MultiSelect.vue';

interface QueueRow {
  lotId: string;
  workflowName: string;
  packageLef: string | null;
  pjType: string | null;
  waferLot: string | null;
  uts: string | null;
  qty: number;
  bop: string | null;
  produceRegion: string | null;
  eqpPackageLef: string | null;
  eqpPjType: string | null;
  eqpWaferLot: string | null;
  eqpUts: string | null;
  targetSpec: string;
  equipment: string;
  matchSource: 'workflow' | 'bop-fallback' | 'none';
}

interface LotEntry {
  lotId: string;
  workflowName: string;
  packageLef: string | null;
  pjType: string | null;
  waferLot: string | null;
  uts: string | null;
  qty: number;
  bop: string | null;
  matchSource: 'workflow' | 'bop-fallback';
  // key = priority group id; value = sorted equipment IDs
  priorityMap: Record<string, string[]>;
}

type PriorityGroup = 'pkg_type_wl' | 'pkg_type' | 'pkg_wl' | 'pkg' | 'none';

const PRIORITY_COLS: { key: PriorityGroup; label: string }[] = [
  { key: 'pkg_type_wl', label: 'Package+Type+Wafer Lot' },
  { key: 'pkg_type',    label: 'Package+Type' },
  { key: 'pkg_wl',      label: 'Package+Wafer Lot' },
  { key: 'pkg',         label: 'Package' },
  // 'none' group is intentionally excluded — machines with no field similarity are not surfaced
];

const loading = ref(false);
const error = ref('');
const rows = ref<QueueRow[]>([]);

// ── Filters ─────────────────────────────────────────────────────────────────
const filterRegion = ref<string[]>([]);
const filterPackageLef = ref<string[]>([]);
const filterType = ref<string[]>([]);

const hasFilter = computed(() =>
  filterRegion.value.length > 0 ||
  filterPackageLef.value.length > 0 ||
  filterType.value.length > 0,
);

// Cross-filter option sets — each filter's options narrow based on the other two.
// We deduplicate per lot via a Set; multiple rows per lot share the same lot-level fields.
function uniqueSorted(vals: (string | null)[]): string[] {
  return [...new Set(vals.filter((v): v is string => v !== null && v !== ''))].sort();
}

const regionOptions = computed(() =>
  uniqueSorted(
    rows.value
      .filter(r =>
        (filterPackageLef.value.length === 0 || filterPackageLef.value.includes(r.packageLef ?? '')) &&
        (filterType.value.length === 0 || filterType.value.includes(r.pjType ?? '')),
      )
      .map(r => r.produceRegion),
  ),
);

const packageLefOptions = computed(() =>
  uniqueSorted(
    rows.value
      .filter(r =>
        (filterRegion.value.length === 0 || filterRegion.value.includes(r.produceRegion ?? '')) &&
        (filterType.value.length === 0 || filterType.value.includes(r.pjType ?? '')),
      )
      .map(r => r.packageLef),
  ),
);

const typeOptions = computed(() =>
  uniqueSorted(
    rows.value
      .filter(r =>
        (filterRegion.value.length === 0 || filterRegion.value.includes(r.produceRegion ?? '')) &&
        (filterPackageLef.value.length === 0 || filterPackageLef.value.includes(r.packageLef ?? '')),
      )
      .map(r => r.pjType),
  ),
);

// Only expose rows when at least one filter is active; filter applies to waiting-lot fields.
const filteredRows = computed((): QueueRow[] => {
  if (!hasFilter.value) return [];
  return rows.value.filter(r =>
    (filterRegion.value.length === 0 || filterRegion.value.includes(r.produceRegion ?? '')) &&
    (filterPackageLef.value.length === 0 || filterPackageLef.value.includes(r.packageLef ?? '')) &&
    (filterType.value.length === 0 || filterType.value.includes(r.pjType ?? '')),
  );
});

async function fetchQueue(): Promise<void> {
  loading.value = true;
  error.value = '';
  try {
    const res = await fetch('/api/db-scheduling/queue', { cache: 'no-store' });
    if (!res.ok) {
      error.value = `載入失敗（HTTP ${res.status}）`;
      return;
    }
    const json = await res.json();
    if (!json.success) {
      error.value = json.error?.message ?? '載入失敗';
      return;
    }
    rows.value = Array.isArray(json.data) ? json.data : [];
  } catch {
    error.value = '無法連線至伺服器，請稍後再試。';
  } finally {
    loading.value = false;
  }
}

onMounted(fetchQueue);

function compareNullsLast(a: string | null, b: string | null): number {
  if (a === b) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return a < b ? -1 : 1;
}

// Classify a candidate machine into a priority group by comparing
// the running lot's attributes against the waiting lot's attributes.
// Null fields on the waiting lot side can never match.
function priorityGroup(
  lotPackageLef: string | null,
  lotPjType: string | null,
  lotWaferLot: string | null,
  row: QueueRow,
): PriorityGroup {
  const pkgMatch  = lotPackageLef !== null && lotPackageLef === row.eqpPackageLef;
  if (!pkgMatch) return 'none';
  const typeMatch = lotPjType    !== null && lotPjType    === row.eqpPjType;
  const wlMatch   = lotWaferLot  !== null && lotWaferLot  === row.eqpWaferLot;
  if (typeMatch && wlMatch) return 'pkg_type_wl';
  if (typeMatch)             return 'pkg_type';
  if (wlMatch)               return 'pkg_wl';
  return 'pkg';
}

// One entry per waiting lot; Map preserves backend sort order.
const lotEntries = computed((): LotEntry[] => {
  const lotMap = new Map<string, QueueRow[]>();
  for (const row of filteredRows.value) {
    if (!lotMap.has(row.lotId)) lotMap.set(row.lotId, []);
    lotMap.get(row.lotId)!.push(row);
  }

  return Array.from(lotMap.entries()).map(([, lotRows]) => {
    const first = lotRows[0];

    // Group machines by similarity; within each group sort by eqpUts ASC NULLS LAST.
    type Item = { equipment: string; eqpUts: string | null };
    const temp: Partial<Record<PriorityGroup, Item[]>> = {};
    for (const row of lotRows) {
      const grp = priorityGroup(first.packageLef, first.pjType, first.waferLot, row);
      if (!temp[grp]) temp[grp] = [];
      temp[grp]!.push({ equipment: row.equipment, eqpUts: row.eqpUts });
    }

    const priorityMap: Record<string, string[]> = {};
    for (const grp in temp) {
      priorityMap[grp] = temp[grp as PriorityGroup]!
        .sort((a, b) => compareNullsLast(a.eqpUts, b.eqpUts))
        .map(i => i.equipment);
    }

    return {
      lotId: first.lotId,
      workflowName: first.workflowName,
      packageLef: first.packageLef,
      pjType: first.pjType,
      waferLot: first.waferLot,
      uts: first.uts,
      qty: first.qty,
      bop: first.bop,
      matchSource: lotRows.some(r => r.matchSource === 'workflow') ? 'workflow' : 'bop-fallback',
      priorityMap,
    };
  });
});

const visibleCols = PRIORITY_COLS;

// ── Cell expand / collapse ──────────────────────────────────────────────────
// Each key is `${lotId}::${groupKey}`. Vue 3 reactive() wraps Set natively.
const expandedCells = reactive(new Set<string>());

function cellKey(lotId: string, groupKey: string): string {
  return `${lotId}::${groupKey}`;
}
function toggleCell(lotId: string, groupKey: string): void {
  const k = cellKey(lotId, groupKey);
  if (expandedCells.has(k)) expandedCells.delete(k);
  else expandedCells.add(k);
}
function isCellExpanded(lotId: string, groupKey: string): boolean {
  return expandedCells.has(cellKey(lotId, groupKey));
}

const PILL_PREVIEW = 2; // pills shown before "+N" overflow button

function matchSourceLabel(src: 'workflow' | 'bop-fallback'): string {
  return src === 'workflow' ? 'Workflow' : 'BOP 回退';
}
function matchSourceClass(src: 'workflow' | 'bop-fallback'): string {
  return src === 'workflow' ? 'match-badge badge-success' : 'match-badge badge-warning';
}

// ── Pill detail popup ───────────────────────────────────────────────────────

interface MachineStatus {
  e10Status: string | null;
  e10Reason: string | null;
  jobOrder: string | null;
  jobModel: string | null;
  jobStage: string | null;
  jobId: string | null;
  jobStatus: string | null;
}

interface LotInfo {
  lotId: string | null;
  workorder: string | null;
  wipStatus: string | null;
  runcardStatus: string | null;
  qty: number | null;
  waferLotQty: number | null;
  ageByDays: number | null;
  priorityCodeName: string | null;
  productName: string | null;
  package: string | null;
  packageLef: string | null;
  pjType: string | null;
  pjFunction: string | null;
  bop: string | null;
  dateCodeReq: string | null;
  produceRegion: string | null;
}

interface PillDetail {
  open: boolean;
  equipment: string;
  loading: boolean;
  error: string;
  machineStatus: MachineStatus | null;
  lotInfo: LotInfo | null;
}

const pillDetail = reactive<PillDetail>({
  open: false,
  equipment: '',
  loading: false,
  error: '',
  machineStatus: null,
  lotInfo: null,
});

function closePillDetail(): void {
  pillDetail.open = false;
}

async function openPillDetail(event: Event, equipment: string): Promise<void> {
  event.stopPropagation();
  pillDetail.open = true;
  pillDetail.equipment = equipment;
  pillDetail.loading = true;
  pillDetail.error = '';
  pillDetail.machineStatus = null;
  pillDetail.lotInfo = null;

  try {
    const res = await fetch(
      `/api/db-scheduling/equipment-detail?equipment=${encodeURIComponent(equipment)}`,
      { cache: 'no-store' },
    );
    const json = await res.json();
    if (!json.success) {
      pillDetail.error = json.error?.message ?? '載入失敗';
      return;
    }
    pillDetail.machineStatus = json.data.machineStatus ?? null;
    pillDetail.lotInfo = json.data.lotInfo ?? null;
  } catch {
    pillDetail.error = '無法連線至伺服器';
  } finally {
    pillDetail.loading = false;
  }
}

function handleEscKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') closePillDetail();
}
onMounted(() => document.addEventListener('keydown', handleEscKey));
onUnmounted(() => document.removeEventListener('keydown', handleEscKey));

function displayVal(v: string | number | null | undefined): string {
  return v !== null && v !== undefined && String(v) !== '' ? String(v) : '—';
}

function e10StatusClass(status: string | null): string {
  if (!status) return '';
  const s = status.toUpperCase();
  if (s === 'PRD') return 'e10-prd';
  if (s === 'SBY') return 'e10-sby';
  if (['UDT', 'SDT'].includes(s)) return 'e10-down';
  if (s === 'NST') return 'e10-nst';
  return 'e10-other';
}
</script>

<template>
  <div class="theme-db-scheduling">
    <div class="page-header">
      <div class="page-title-block">
        <h1 class="page-title">DB 生產排程助手</h1>
        <p class="page-subtitle">D/B-START 批次設備推薦清單</p>
      </div>
      <button
        class="btn-refresh"
        :disabled="loading"
        aria-label="重新整理資料"
        @click="fetchQueue"
      >
        重新整理
      </button>
    </div>

    <div v-if="loading" class="loading-state" role="status" aria-live="polite">
      <span class="loading-spinner" aria-hidden="true"></span>
      <span>載入中…</span>
    </div>

    <div v-else-if="error" class="error-state" role="alert">
      <span class="error-icon" aria-hidden="true">⚠</span>
      <span>{{ error }}</span>
    </div>

    <template v-else>
      <!-- Filter bar — always visible after data loads -->
      <div class="filter-bar">
        <div class="filter-item">
          <label class="filter-label">區域</label>
          <MultiSelect
            v-model="filterRegion"
            :options="regionOptions"
            placeholder="全部區域"
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">Package LEF</label>
          <MultiSelect
            v-model="filterPackageLef"
            :options="packageLefOptions"
            placeholder="全部 Package LEF"
          />
        </div>
        <div class="filter-item">
          <label class="filter-label">Type</label>
          <MultiSelect
            v-model="filterType"
            :options="typeOptions"
            placeholder="全部 Type"
          />
        </div>
      </div>

      <!-- No filter selected yet -->
      <div v-if="!hasFilter" class="filter-hint" data-testid="db-scheduling-filter-hint">
        請先設定篩選條件以顯示推薦清單。
      </div>

      <!-- Filter active but no results -->
      <div v-else-if="lotEntries.length === 0" class="empty-state" data-testid="db-scheduling-empty">
        目前沒有符合條件的 D/B-START 批次。
      </div>

      <!-- Table -->
      <div v-else class="table-wrap">
      <table class="data-table" data-testid="db-scheduling-table">
        <thead>
          <!-- Level 1: group headers -->
          <tr class="group-header-row">
            <th colspan="8" class="group-header group-lot">待排單</th>
            <th colspan="1" class="group-header group-match">匹配方式</th>
            <th :colspan="visibleCols.length" class="group-header group-priority">匹配優先度</th>
          </tr>
          <!-- Level 2: column names -->
          <tr>
            <th>LOT ID</th>
            <th>BOP</th>
            <th>Workflow</th>
            <th>Package LEF</th>
            <th>PJ Type</th>
            <th>Wafer Lot</th>
            <th>完工日期</th>
            <th>數量</th>
            <th></th>
            <th
              v-for="col in visibleCols"
              :key="col.key"
              class="priority-col-header"
              :class="`priority-${col.key}`"
            >{{ col.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="lot in lotEntries" :key="lot.lotId">
            <td>{{ lot.lotId }}</td>
            <td>{{ lot.bop ?? '—' }}</td>
            <td>{{ lot.workflowName }}</td>
            <td>{{ lot.packageLef ?? '—' }}</td>
            <td>{{ lot.pjType ?? '—' }}</td>
            <td>{{ lot.waferLot ?? '—' }}</td>
            <td>{{ lot.uts ?? '—' }}</td>
            <td>{{ lot.qty }}</td>
            <td>
              <span
                :class="matchSourceClass(lot.matchSource)"
                data-testid="match-source-badge"
              >{{ matchSourceLabel(lot.matchSource) }}</span>
            </td>
            <td
              v-for="col in visibleCols"
              :key="col.key"
              class="machine-cell"
              :class="{ 'cell-expandable': (lot.priorityMap[col.key]?.length ?? 0) > PILL_PREVIEW }"
              @click="(lot.priorityMap[col.key]?.length ?? 0) > PILL_PREVIEW && toggleCell(lot.lotId, col.key)"
            >
              <template v-if="lot.priorityMap[col.key]?.length">
                <!-- Preview: always show first PILL_PREVIEW pills -->
                <div class="pills-preview">
                  <span
                    v-for="eqp in lot.priorityMap[col.key].slice(0, PILL_PREVIEW)"
                    :key="eqp"
                    class="machine-pill"
                    role="button"
                    tabindex="0"
                    @click.stop="openPillDetail($event, eqp)"
                    @keydown.enter.stop="openPillDetail($event, eqp)"
                  >{{ eqp }}</span>
                  <!-- Overflow badge when collapsed -->
                  <span
                    v-if="lot.priorityMap[col.key].length > PILL_PREVIEW && !isCellExpanded(lot.lotId, col.key)"
                    class="pill-overflow"
                    :title="`展開查看另外 ${lot.priorityMap[col.key].length - PILL_PREVIEW} 台`"
                  >+{{ lot.priorityMap[col.key].length - PILL_PREVIEW }}</span>
                </div>
                <!-- Expanded: remaining pills in 2-column grid -->
                <div
                  v-if="isCellExpanded(lot.lotId, col.key)"
                  class="pills-grid"
                >
                  <span
                    v-for="eqp in lot.priorityMap[col.key].slice(PILL_PREVIEW)"
                    :key="eqp"
                    class="machine-pill"
                    role="button"
                    tabindex="0"
                    @click.stop="openPillDetail($event, eqp)"
                    @keydown.enter.stop="openPillDetail($event, eqp)"
                  >{{ eqp }}</span>
                </div>
              </template>
              <span v-else class="cell-empty" aria-hidden="true">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    </template>
  </div>

  <!-- Machine pill detail popup (Teleport keeps it above table overflow) -->
  <Teleport to="body">
    <div v-if="pillDetail.open" class="theme-db-scheduling">
      <div class="pill-detail-overlay" role="dialog" aria-modal="true" @click.self="closePillDetail">
        <div class="pill-detail-card">
          <!-- Header -->
          <div class="pill-detail-header">
            <span class="pill-detail-title">{{ pillDetail.equipment }}</span>
            <button class="pill-detail-close" aria-label="關閉" @click="closePillDetail">✕</button>
          </div>

          <!-- Loading -->
          <div v-if="pillDetail.loading" class="pill-detail-loading">
            <span class="loading-spinner" aria-hidden="true"></span>
            <span>載入中…</span>
          </div>

          <!-- Error -->
          <div v-else-if="pillDetail.error" class="pill-detail-error">{{ pillDetail.error }}</div>

          <!-- Content -->
          <template v-else>
            <!-- Machine Status -->
            <div class="pill-detail-section">
              <div class="pill-detail-section-title">機台狀態</div>
              <div class="pill-detail-grid">
                <span class="pd-label">E10 狀態</span>
                <span class="pd-value">
                  <span
                    v-if="pillDetail.machineStatus?.e10Status"
                    class="e10-badge"
                    :class="e10StatusClass(pillDetail.machineStatus.e10Status)"
                  >{{ pillDetail.machineStatus.e10Status }}</span>
                  <span v-else>—</span>
                </span>

                <span class="pd-label">狀態原因</span>
                <span class="pd-value">{{ displayVal(pillDetail.machineStatus?.e10Reason) }}</span>

                <template v-if="pillDetail.machineStatus?.jobOrder">
                  <span class="pd-label">JOB 單號</span>
                  <span class="pd-value">{{ displayVal(pillDetail.machineStatus.jobOrder) }}</span>

                  <span class="pd-label">JOB 狀態</span>
                  <span class="pd-value">{{ displayVal(pillDetail.machineStatus.jobStatus) }}</span>

                  <span class="pd-label">JOB Model</span>
                  <span class="pd-value">{{ displayVal(pillDetail.machineStatus.jobModel) }}</span>

                  <span class="pd-label">JOB Stage</span>
                  <span class="pd-value">{{ displayVal(pillDetail.machineStatus.jobStage) }}</span>
                </template>
              </div>
            </div>

            <!-- Running Lot Info -->
            <template v-if="pillDetail.lotInfo">
              <div class="pill-detail-section">
                <div class="pill-detail-section-title">基本資訊</div>
                <div class="pill-detail-grid">
                  <span class="pd-label">Run Card Lot ID</span>
                  <span class="pd-value pd-mono">{{ displayVal(pillDetail.lotInfo.lotId) }}</span>

                  <span class="pd-label">Work Order ID</span>
                  <span class="pd-value pd-mono">{{ displayVal(pillDetail.lotInfo.workorder) }}</span>

                  <span class="pd-label">WIP Status</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.wipStatus) }}</span>

                  <span class="pd-label">Run Card Status</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.runcardStatus) }}</span>

                  <span class="pd-label">Lot Qty (pcs)</span>
                  <span class="pd-value">{{ pillDetail.lotInfo.qty !== null ? pillDetail.lotInfo.qty.toLocaleString() : '—' }}</span>

                  <span class="pd-label">Lot Qty (Wafer pcs)</span>
                  <span class="pd-value">{{ pillDetail.lotInfo.waferLotQty !== null ? pillDetail.lotInfo.waferLotQty.toLocaleString() : '—' }}</span>

                  <span class="pd-label">Age By Days</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.ageByDays) }}</span>

                  <span class="pd-label">Work Order Priority</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.priorityCodeName) }}</span>
                </div>
              </div>

              <div class="pill-detail-section">
                <div class="pill-detail-section-title">產品資訊</div>
                <div class="pill-detail-grid">
                  <span class="pd-label">Product P/N</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.productName) }}</span>

                  <span class="pd-label">Package</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.package) }}</span>

                  <span class="pd-label">Package (LF)</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.packageLef) }}</span>

                  <span class="pd-label">Product Type</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.pjType) }}</span>

                  <span class="pd-label">Product Function</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.pjFunction) }}</span>

                  <span class="pd-label">BOP</span>
                  <span class="pd-value pd-mono">{{ displayVal(pillDetail.lotInfo.bop) }}</span>

                  <span class="pd-label">Product Date Code</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.dateCodeReq) }}</span>

                  <span class="pd-label">Produce Region</span>
                  <span class="pd-value">{{ displayVal(pillDetail.lotInfo.produceRegion) }}</span>
                </div>
              </div>
            </template>

            <div v-else class="pill-detail-no-lot">
              此機台目前無在製 LOT（可能已停機或無 WIP 紀錄）。
            </div>
          </template>
        </div>
      </div>
    </div>
  </Teleport>
</template>
