<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue';

import { apiGet } from '../../core/api';

interface LotItem {
  RUNCARDLOTID?: string;
  LOTTRACKINQTY_PCS?: number | null;
  LOTTRACKINTIME?: string | null;
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

const tooltipRef = ref<HTMLElement | null>(null);
const tooltipStyle = reactive<{ left: string; top: string }>({ left: '0px', top: '0px' });
const lotDetailMap = ref<Record<string, LotDetail>>({});
const isDragging = ref(false);
const dragOffset: { x: number; y: number } = { x: 0, y: 0 };

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
  if (ids.length === 0) {
    return;
  }

  const pending = ids.filter((id: string) => !lotDetailMap.value[id]);
  if (pending.length === 0) {
    return;
  }

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

function lotDetailValue(detail: LotDetail | null, key: string): string {
  const value = detail?.[key];
  if (value === null || value === undefined || value === '') {
    return '--';
  }
  return String(value);
}

interface JobField {
  label: string;
  value: string | undefined;
  highlight?: boolean;
}

const jobFields = computed<JobField[]>(() => {
  if (!props.payload || Array.isArray(props.payload)) {
    return [];
  }

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
  if (!rawValue) {
    return '--';
  }
  try {
    return new Date(rawValue).toLocaleString('zh-TW');
  } catch {
    return String(rawValue);
  }
}

function positionTooltip() {
  if (!props.visible || !tooltipRef.value) {
    return;
  }

  const padding = 10;
  const width = tooltipRef.value.offsetWidth;
  const height = tooltipRef.value.offsetHeight;

  let nextX = Number(props.position?.x || 0) + 12;
  let nextY = Number(props.position?.y || 0) + 12;

  if (nextX + width > window.innerWidth - padding) {
    nextX = window.innerWidth - width - padding;
  }
  if (nextY + height > window.innerHeight - padding) {
    nextY = window.innerHeight - height - padding;
  }

  nextX = Math.max(padding, nextX);
  nextY = Math.max(padding, nextY);

  tooltipStyle.left = `${nextX}px`;
  tooltipStyle.top = `${nextY}px`;
}

function handleOutsideClick(event: MouseEvent): void {
  if (!props.visible || !tooltipRef.value) {
    return;
  }
  if (!tooltipRef.value.contains(event.target as Node)) {
    emit('close');
  }
}

function onDragStart(event: MouseEvent): void {
  if (event.button !== 0) {
    return;
  }
  isDragging.value = true;
  dragOffset.x = event.clientX - parseFloat(tooltipStyle.left);
  dragOffset.y = event.clientY - parseFloat(tooltipStyle.top);
  document.addEventListener('mousemove', onDragMove);
  document.addEventListener('mouseup', onDragEnd);
}

function onDragMove(event: MouseEvent): void {
  if (!isDragging.value) {
    return;
  }
  const padding = 10;
  let nextX = event.clientX - dragOffset.x;
  let nextY = event.clientY - dragOffset.y;

  nextX = Math.max(padding, Math.min(nextX, window.innerWidth - padding));
  nextY = Math.max(padding, Math.min(nextY, window.innerHeight - padding));

  tooltipStyle.left = `${nextX}px`;
  tooltipStyle.top = `${nextY}px`;
}

function onDragEnd() {
  isDragging.value = false;
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', onDragEnd);
}

function bindOverlayListeners() {
  document.addEventListener('click', handleOutsideClick, true);
  window.addEventListener('resize', positionTooltip);
}

function unbindOverlayListeners() {
  document.removeEventListener('click', handleOutsideClick, true);
  window.removeEventListener('resize', positionTooltip);
  document.removeEventListener('mousemove', onDragMove);
  document.removeEventListener('mouseup', onDragEnd);
}

watch(
  () => [props.visible, props.position?.x, props.position?.y, props.payload],
  async ([visible]) => {
    if (!visible) {
      unbindOverlayListeners();
      return;
    }

    await nextTick();
    positionTooltip();
    bindOverlayListeners();

    if (props.type === 'lot' && Array.isArray(props.payload) && props.payload.length > 0) {
      void fetchLotDetails(props.payload);
    }
  }
);

onBeforeUnmount(() => {
  unbindOverlayListeners();
});
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" ref="tooltipRef" class="floating-tooltip" :style="tooltipStyle" @click.stop>
      <div class="floating-tooltip-header" :class="{ dragging: isDragging }" @mousedown="onDragStart">
        <h3 class="floating-tooltip-title">{{ tooltipTitle }}</h3>
        <button type="button" class="floating-tooltip-close" @click="$emit('close')">&times;</button>
      </div>

      <div class="floating-tooltip-body">
        <template v-if="type === 'lot'">
          <template v-if="lotItems.length">
            <article v-for="(lot, index) in lotItems" :key="`${lot.RUNCARDLOTID || 'lot'}-${index}`" class="lot-item">
              <div class="lot-item-id">{{ lot.RUNCARDLOTID || '--' }}</div>
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

              <template v-if="getLotDetail(lot.RUNCARDLOTID)">
                <div class="lot-section-label">產品資訊</div>
                <div class="lot-grid">
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Product</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'product') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Product Line</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'productLine') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Package</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'packageLef') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Workorder</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'workorder') }}</span>
                  </div>
                </div>

                <div class="lot-section-label">物料資訊</div>
                <div class="lot-grid">
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Wafer Lot ID</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'waferLotId') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Wafer P/N</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'waferPn') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Wafer Description</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'waferDesc') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Leadframe</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'leadframeName') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">LF Description</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'leadframeDesc') }}</span>
                  </div>
                  <div class="tooltip-field">
                    <span class="tooltip-field-label">Compound</span>
                    <span class="tooltip-field-value">{{ lotDetailValue(getLotDetail(lot.RUNCARDLOTID), 'compoundName') }}</span>
                  </div>
                </div>
              </template>
              <div v-else-if="lot.RUNCARDLOTID" class="lot-detail-loading-hint">載入詳細資料中...</div>
            </article>
          </template>
          <div v-else class="tooltip-empty">無 LOT 明細</div>
        </template>

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
    </div>
  </Teleport>
</template>
