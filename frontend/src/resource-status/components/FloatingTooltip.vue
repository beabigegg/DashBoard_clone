<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue';

const props = defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  type: {
    type: String,
    default: 'lot',
  },
  payload: {
    type: [Array, Object],
    default: null,
  },
  position: {
    type: Object,
    default: () => ({ x: 0, y: 0 }),
  },
});

const emit = defineEmits(['close']);

const tooltipRef = ref(null);
const tooltipStyle = reactive({ left: '0px', top: '0px' });

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

const jobFields = computed(() => {
  if (!props.payload || Array.isArray(props.payload)) {
    return [];
  }

  const eq = props.payload;
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

function formatDate(rawValue) {
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

function handleOutsideClick(event) {
  if (!props.visible || !tooltipRef.value) {
    return;
  }
  if (!tooltipRef.value.contains(event.target)) {
    emit('close');
  }
}

function bindOverlayListeners() {
  document.addEventListener('click', handleOutsideClick, true);
  window.addEventListener('resize', positionTooltip);
}

function unbindOverlayListeners() {
  document.removeEventListener('click', handleOutsideClick, true);
  window.removeEventListener('resize', positionTooltip);
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
  }
);

onBeforeUnmount(() => {
  unbindOverlayListeners();
});
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" ref="tooltipRef" class="floating-tooltip" :style="tooltipStyle" @click.stop>
      <div class="floating-tooltip-header">
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
                <div class="tooltip-field">
                  <span class="tooltip-field-label">Employee</span>
                  <span class="tooltip-field-value">{{ lot.LOTTRACKINEMPLOYEE || '--' }}</span>
                </div>
              </div>
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
