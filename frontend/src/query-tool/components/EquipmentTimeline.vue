<script setup>
import { computed } from 'vue';

import TimelineChart from '../../shared-ui/components/TimelineChart.vue';
import ExportButton from './ExportButton.vue';
import { normalizeText, parseDateTime } from '../utils/values.js';

const props = defineProps({
  statusRows: {
    type: Array,
    default: () => [],
  },
  lotsRows: {
    type: Array,
    default: () => [],
  },
  jobsRows: {
    type: Array,
    default: () => [],
  },
  equipmentOptions: {
    type: Array,
    default: () => [],
  },
  selectedEquipmentIds: {
    type: Array,
    default: () => [],
  },
  startDate: {
    type: String,
    default: '',
  },
  endDate: {
    type: String,
    default: '',
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
  exportDisabled: {
    type: Boolean,
    default: true,
  },
  exporting: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['export']);

const STATUS_KEYS = Object.freeze(['PRD', 'SBY', 'UDT', 'SDT']);

const colorMap = Object.freeze({
  PRD: '#16a34a',
  SBY: '#f59e0b',
  UDT: '#ef4444',
  SDT: '#64748b',
  LOT: '#2563eb',
  JOB: '#9333ea',
});

function toDate(value) {
  const date = parseDateTime(value);
  return date ? date : null;
}

const range = computed(() => {
  const start = toDate(props.startDate);
  const end = toDate(props.endDate);
  if (!start || !end) {
    return null;
  }

  const normalizedEnd = new Date(end);
  normalizedEnd.setHours(23, 59, 59, 999);

  return {
    start,
    end: normalizedEnd,
  };
});

function resolveEquipmentLabel(equipmentId) {
  const id = normalizeText(equipmentId);
  if (!id) {
    return '';
  }

  const match = props.equipmentOptions.find((item) => {
    const resourceId = normalizeText(item?.RESOURCEID || item?.value);
    return resourceId === id;
  });

  const resourceName = normalizeText(match?.RESOURCENAME || match?.label);
  if (resourceName) {
    return `${resourceName} (${id})`;
  }
  return id;
}

const tracks = computed(() => {
  if (!range.value) {
    return [];
  }

  return props.selectedEquipmentIds.map((equipmentId) => {
    const id = normalizeText(equipmentId);
    const label = resolveEquipmentLabel(id);

    const statusRow = props.statusRows.find((row) => normalizeText(row?.RESOURCEID) === id);

    const statusBars = [];
    let cursor = range.value.start.getTime();

    STATUS_KEYS.forEach((status) => {
      const hours = Number(statusRow?.[`${status}_HOURS`] || 0);
      if (!Number.isFinite(hours) || hours <= 0) {
        return;
      }

      const durationMs = hours * 60 * 60 * 1000;
      const endMs = Math.min(cursor + durationMs, range.value.end.getTime());
      statusBars.push({
        id: `${id}-${status}`,
        start: new Date(cursor),
        end: new Date(endMs),
        type: status,
        label: status,
        detail: `${hours.toFixed(2)}h`,
      });
      cursor = endMs;
    });

    const lotBars = props.lotsRows
      .filter((row) => normalizeText(row?.EQUIPMENTID) === id)
      .map((row, index) => {
        const start = toDate(row?.TRACKINTIMESTAMP);
        const end = toDate(row?.TRACKOUTTIMESTAMP) || (start ? new Date(start.getTime() + (1000 * 60 * 30)) : null);
        if (!start || !end) {
          return null;
        }
        return {
          id: `${id}-lot-${index}`,
          start,
          end,
          type: 'LOT',
          label: normalizeText(row?.CONTAINERNAME || row?.CONTAINERID) || 'LOT',
          detail: `${normalizeText(row?.SPECNAME)} / ${normalizeText(row?.WORKCENTERNAME)}`,
        };
      })
      .filter(Boolean);

    return {
      id,
      label,
      layers: [
        {
          id: `${id}-status`,
          bars: statusBars,
          opacity: 0.45,
        },
        {
          id: `${id}-lots`,
          bars: lotBars,
          opacity: 0.92,
        },
      ],
    };
  });
});

const events = computed(() => {
  return props.jobsRows
    .map((row, index) => {
      const equipmentId = normalizeText(row?.RESOURCEID);
      if (!equipmentId || !props.selectedEquipmentIds.includes(equipmentId)) {
        return null;
      }

      const time = toDate(row?.CREATEDATE) || toDate(row?.COMPLETEDATE);
      if (!time) {
        return null;
      }

      return {
        id: `${equipmentId}-job-${index}`,
        trackId: equipmentId,
        time,
        type: 'JOB',
        shape: 'triangle',
        label: `${normalizeText(row?.JOBID)} ${normalizeText(row?.CAUSECODENAME)}`.trim(),
        detail: `${normalizeText(row?.REPAIRCODENAME)} / ${normalizeText(row?.SYMPTOMCODENAME)} / ${normalizeText(row?.CONTAINERNAMES)}`,
      };
    })
    .filter(Boolean);
});

const showEmpty = computed(() => tracks.value.length === 0 || (tracks.value.every((track) => {
  const statusLayer = track.layers[0]?.bars || [];
  const lotLayer = track.layers[1]?.bars || [];
  return statusLayer.length === 0 && lotLayer.length === 0;
}) && events.value.length === 0));
</script>

<template>
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title ui-card-title">設備 Timeline</h4>
      <ExportButton
        :disabled="exportDisabled"
        :loading="exporting"
        label="匯出狀態時數"
        @click="emit('export')"
      />
    </div>

    <p v-if="error" class="error-banner">
      {{ error }}
    </p>

    <div v-if="loading" class="placeholder">
      Timeline 資料載入中...
    </div>

    <div v-else-if="showEmpty" class="placeholder">
      無 Timeline 資料
    </div>

    <TimelineChart
      v-else
      :tracks="tracks"
      :events="events"
      :time-range="range"
      :color-map="colorMap"
      :track-row-height="48"
      :label-width="220"
      :min-chart-width="1200"
    />
  </div>
</template>
