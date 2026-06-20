<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';

import { apiGet } from '../../core/api';

interface LotItem {
  RUNCARDLOTID?: string;
  LOTTRACKINQTY_PCS?: number | null;
  LOTTRACKINTIME?: string | null;
  LOTTRACKINEMPLOYEE?: string | null;
  // Product/material fields from DW_MES_EQUIPMENTSTATUS_WIP_V (available immediately)
  PACKAGE?: string | null;
  PACKAGE_LF?: string | null;
  SPEC?: string | null;
  TYPE?: string | null;
  FUNCTION?: string | null;
  BOP?: string | null;
  WAFERLOTID?: string | null;
  WAFERPN?: string | null;
  WAFERLOTID_PREFIX?: string | null;
  LFOPTIONID?: string | null;
  WIREDESCRIPTION?: string | null;
  WAFERMIL?: string | null;
}

interface LotDetail {
  [key: string]: string | number | null | undefined;
}

interface EquipmentItem {
  RESOURCEID: string;
  RESOURCENAME: string;
  EQUIPMENTASSETSSTATUS: string;
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  RESOURCEFAMILYNAME: string;
  WORKCENTERNAME: string;
  LOCATIONNAME: string;
  LOT_COUNT: number | string;
  LOT_DETAILS: LotItem[];
  JOBORDER: string;
  JOBSTATUS: string;
  JOBMODEL: string;
  JOBSTAGE: string;
  JOBID: string;
  CREATEDATE: string;
  CREATEUSERNAME: string;
  CREATEUSER: string;
  TECHNICIANUSERNAME: string;
  TECHNICIANUSER: string;
  SYMPTOMCODE: string;
  CAUSECODE: string;
  REPAIRCODE: string;
  STATUS_CATEGORY: string;
}

const props = withDefaults(defineProps<{
  visible?: boolean;
  type?: 'lot' | 'job';
  payload?: LotItem[] | EquipmentItem | null;
  position?: { x: number; y: number };
}>(), {
  visible: false,
  type: 'lot',
  payload: null,
  position: () => ({ x: 0, y: 0 }),
});

const emit = defineEmits<{
  close: [];
}>();

const panelRef = ref<HTMLElement | null>(null);
const lotDetailMap = ref<Record<string, LotDetail>>({});

const tooltipTitle = computed(() => {
  if (props.type === 'job') {
    return 'JOB 詳細資訊';
  }
  return 'LOT 詳情';
});

const lotItems = computed(() => {
  if (!Array.isArray(props.payload)) {
    return [];
  }
  return props.payload;
});

async function fetchLotDetails(lots: LotItem[]): Promise<void> {
  const ids = lots.map((lot) => lot.RUNCARDLOTID).filter((id): id is string => Boolean(id));
  if (ids.length === 0) return;

  const pending = ids.filter((id: string) => !lotDetailMap.value[id]);
  if (pending.length === 0) return;

  const results = await Promise.allSettled(
    pending.map((id: string) =>
      apiGet(`/api/wip/lot/${encodeURIComponent(id)}`, { timeout: 15000 })
        .then((result) => {
          const r = result as { success?: boolean; data?: unknown } | null;
          const data = r?.success ? r.data : r?.data !== undefined ? r.data : result;
          return { id, data };
        }),
    ),
  );

  const updated: Record<string, LotDetail> = { ...lotDetailMap.value };
  for (const entry of results) {
    if (entry.status === 'fulfilled' && entry.value?.data) {
      updated[entry.value.id] = entry.value.data as LotDetail;
    }
  }
  lotDetailMap.value = updated;
}

function getLotDetail(lotId: string | undefined): LotDetail | null {
  if (!lotId) return null;
  return lotDetailMap.value[lotId] || null;
}

function val(detail: LotDetail | null, key: string): string {
  const v = detail?.[key];
  if (v === null || v === undefined || v === '') return '--';
  return String(v);
}

function lotVal(lot: LotItem, key: keyof LotItem): string {
  const v = lot[key];
  if (v === null || v === undefined || v === '') return '--';
  return String(v);
}

// Prefers lot-detail API value; falls back to WIP_V value on the LotItem
function prefer(
  detail: LotDetail | null,
  detailKey: string,
  lot: LotItem,
  lotKey: keyof LotItem,
): string {
  const dv = detail?.[detailKey];
  if (dv !== null && dv !== undefined && dv !== '') return String(dv);
  return lotVal(lot, lotKey);
}

interface JobField {
  label: string;
  value: string | undefined;
  highlight?: boolean;
}

const jobFields = computed<JobField[]>(() => {
  if (!props.payload || Array.isArray(props.payload)) return [];
  const eq = props.payload as EquipmentItem;
  return [
    { label: 'JOBORDER', value: eq.JOBORDER, highlight: true },
    { label: 'JOBSTATUS', value: eq.JOBSTATUS, highlight: true },
    { label: 'MODEL', value: eq.JOBMODEL },
    { label: 'STAGE', value: eq.JOBSTAGE },
    { label: 'JOBID', value: eq.JOBID },
    { label: '建立時間', value: formatDate(eq.CREATEDATE) },
    { label: '建立人員', value: eq.CREATEUSERNAME || eq.CREATEUSER },
    { label: '技術員', value: eq.TECHNICIANUSERNAME || eq.TECHNICIANUSER },
    { label: '症狀碼', value: eq.SYMPTOMCODE },
    { label: '原因碼', value: eq.CAUSECODE },
    { label: '維修碼', value: eq.REPAIRCODE },
  ];
});

function formatDate(rawValue: string | null | undefined): string {
  if (!rawValue) return '--';
  // Oracle DATE columns serialised as midnight UTC must not be converted via new Date()
  // in non-UTC locales — extract components directly to avoid ±8h TZ shift.
  const m = rawValue.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if (m) {
    const [, y, mo, d, h, min, s] = m;
    if (h === '00' && min === '00' && s === '00') {
      return `${y}/${mo}/${d}`;
    }
    return `${y}/${mo}/${d} ${h}:${min}:${s}`;
  }
  try {
    return new Date(rawValue).toLocaleString('zh-TW');
  } catch {
    return String(rawValue);
  }
}

function handleEscapeKey(event: KeyboardEvent): void {
  if (event.key === 'Escape' && props.visible) {
    emit('close');
  }
}

watch(
  () => [props.visible, props.payload],
  async ([visible]) => {
    if (!visible) {
      document.removeEventListener('keydown', handleEscapeKey);
      return;
    }
    await nextTick();
    document.addEventListener('keydown', handleEscapeKey);

    if (props.type === 'lot' && Array.isArray(props.payload) && props.payload.length > 0) {
      void fetchLotDetails(props.payload);
    }
  },
);

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleEscapeKey);
});
</script>

<template>
  <Teleport to="body">
    <div class="theme-resource">
      <template v-if="visible">
        <!-- Backdrop: click outside panel to close -->
        <div class="tooltip-backdrop" @click="$emit('close')" />

        <!-- Right-side detail panel -->
        <aside ref="panelRef" class="floating-tooltip" data-testid="equipment-tooltip" role="dialog" :aria-label="tooltipTitle" @click.stop>
          <div class="floating-tooltip-header">
            <h3 class="floating-tooltip-title">{{ tooltipTitle }}</h3>
            <button
              type="button"
              class="floating-tooltip-close"
              :aria-label="'關閉'"
              @click="$emit('close')"
            >&times;</button>
          </div>

          <div class="floating-tooltip-body">

            <!-- ── LOT view ── -->
            <template v-if="type === 'lot'">
              <template v-if="lotItems.length">
                <article
                  v-for="(lot, index) in lotItems"
                  :key="`${lot.RUNCARDLOTID || 'lot'}-${index}`"
                  class="lot-item"
                >
                  <div class="lot-item-id">{{ lot.RUNCARDLOTID || '--' }}</div>

                  <!-- Basic (always available) -->
                  <div class="lot-grid">
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">QTY</span>
                      <span class="tooltip-field-value">{{ lot.LOTTRACKINQTY_PCS ?? '--' }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Track-in</span>
                      <span class="tooltip-field-value">{{ formatDate(lot.LOTTRACKINTIME) }}</span>
                    </div>
                  </div>

                  <!-- Product info -->
                  <div class="lot-section-label">產品資訊</div>
                  <div class="lot-grid">
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Product</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'product') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Product Line</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'productLine') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Package</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'packageLef', lot, 'PACKAGE') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Package LF</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'packageLef', lot, 'PACKAGE_LF') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Workorder</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'workorder') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Spec</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'spec', lot, 'SPEC') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">PJ Function</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'pjFunction', lot, 'FUNCTION') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">PJ Type</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'pjType', lot, 'TYPE') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">BOP</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'bop', lot, 'BOP') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Workflow</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'workflow') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Workcenter</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'workcenter') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Date Code</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'dateCode') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">在製天數</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'ageByDays') }}</span>
                    </div>
                  </div>

                  <!-- Material info -->
                  <div class="lot-section-label">物料資訊</div>
                  <div class="lot-grid">
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Wafer Lot ID</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'waferLotId', lot, 'WAFERLOTID_PREFIX') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Wafer P/N</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'waferPn', lot, 'WAFERPN') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Wafer Description</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'waferDesc') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Leadframe</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'leadframeName') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">LF Option</span>
                      <span class="tooltip-field-value">
                        {{ prefer(getLotDetail(lot.RUNCARDLOTID), 'leadframeOption', lot, 'LFOPTIONID') }}
                      </span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">LF Description</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'leadframeDesc') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Compound</span>
                      <span class="tooltip-field-value">{{ val(getLotDetail(lot.RUNCARDLOTID), 'compoundName') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">線材規格</span>
                      <span class="tooltip-field-value">{{ lotVal(lot, 'WIREDESCRIPTION') }}</span>
                    </div>
                    <div class="tooltip-field">
                      <span class="tooltip-field-label">Die Size (mil)</span>
                      <span class="tooltip-field-value">{{ lotVal(lot, 'WAFERMIL') }}</span>
                    </div>
                  </div>

                  <!-- Loading hint: only shown while lot detail API is pending -->
                  <div
                    v-if="lot.RUNCARDLOTID && !getLotDetail(lot.RUNCARDLOTID)"
                    class="lot-detail-loading-hint"
                  >
                    載入詳細資料中...
                  </div>
                </article>
              </template>
              <div v-else class="tooltip-empty">無 LOT 明細</div>
            </template>

            <!-- ── JOB view ── -->
            <template v-else>
              <template v-if="jobFields.length">
                <div class="job-grid">
                  <div v-for="field in jobFields" :key="field.label" class="tooltip-field">
                    <span class="tooltip-field-label">{{ field.label }}</span>
                    <span class="tooltip-field-value" :class="{ highlight: field.highlight }">
                      {{ field.value || '--' }}
                    </span>
                  </div>
                </div>
              </template>
              <div v-else class="tooltip-empty">無 JOB 明細</div>
            </template>

          </div>
        </aside>
      </template>
    </div>
  </Teleport>
</template>
