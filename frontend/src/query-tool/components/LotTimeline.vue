<script setup>
import { computed } from 'vue';

import TimelineChart from '../../shared-ui/components/TimelineChart.vue';
import { formatDateTime, hashColor, normalizeText, parseDateTime } from '../utils/values.js';

const props = defineProps({
  historyRows: {
    type: Array,
    default: () => [],
  },
  holdRows: {
    type: Array,
    default: () => [],
  },
  materialRows: {
    type: Array,
    default: () => [],
  },
});

function safeDate(value) {
  const parsed = parseDateTime(value);
  return parsed ? parsed : null;
}

function fallbackTrackId() {
  const first = props.historyRows[0];
  return normalizeText(first?.WORKCENTERNAME) || 'UNKNOWN_TRACK';
}

const tracks = computed(() => {
  const grouped = new Map();

  props.historyRows.forEach((row, index) => {
    const workcenterName = normalizeText(row?.WORKCENTERNAME) || `WORKCENTER-${index + 1}`;
    const start = safeDate(row?.TRACKINTIMESTAMP);
    const end = safeDate(row?.TRACKOUTTIMESTAMP) || (start ? new Date(start.getTime() + (1000 * 60 * 30)) : null);

    if (!start || !end) {
      return;
    }

    if (!grouped.has(workcenterName)) {
      grouped.set(workcenterName, []);
    }

    grouped.get(workcenterName).push({
      id: `${workcenterName}-${index}`,
      start,
      end,
      type: workcenterName,
      label: row?.SPECNAME || workcenterName,
      detail: `${normalizeText(row?.CONTAINERNAME || row?.CONTAINERID)} | ${normalizeText(row?.EQUIPMENTNAME)}`,
    });
  });

  return [...grouped.entries()].map(([trackId, bars]) => ({
    id: trackId,
    label: trackId,
    layers: [
      {
        id: `${trackId}-lots`,
        bars,
        opacity: 0.85,
      },
    ],
  }));
});

const events = computed(() => {
  const markers = [];

  props.holdRows.forEach((row, index) => {
    const time = safeDate(row?.HOLDTXNDATE);
    if (!time) {
      return;
    }

    markers.push({
      id: `hold-${index}`,
      trackId: normalizeText(row?.WORKCENTERNAME) || fallbackTrackId(),
      time,
      type: 'HOLD',
      shape: 'diamond',
      label: 'Hold',
      detail: `${normalizeText(row?.HOLDREASONNAME)} ${normalizeText(row?.HOLDCOMMENTS)}`.trim(),
    });
  });

  props.materialRows.forEach((row, index) => {
    const time = safeDate(row?.TXNDATE);
    if (!time) {
      return;
    }

    markers.push({
      id: `material-${index}`,
      trackId: normalizeText(row?.WORKCENTERNAME) || fallbackTrackId(),
      time,
      type: 'MATERIAL',
      shape: 'triangle',
      label: normalizeText(row?.MATERIALPARTNAME) || 'Material',
      detail: `Qty ${row?.QTYCONSUMED ?? '-'} / ${normalizeText(row?.MATERIALLOTNAME)}`,
    });
  });

  return markers;
});

const colorMap = computed(() => {
  const colors = {
    HOLD: '#f59e0b',
    MATERIAL: '#0ea5e9',
  };

  tracks.value.forEach((track) => {
    colors[track.id] = hashColor(track.id);
  });

  return colors;
});

const timeRange = computed(() => {
  const timestamps = [];

  tracks.value.forEach((track) => {
    (track.layers || []).forEach((layer) => {
      (layer.bars || []).forEach((bar) => {
        timestamps.push(bar.start?.getTime?.() || 0);
        timestamps.push(bar.end?.getTime?.() || 0);
      });
    });
  });

  events.value.forEach((eventItem) => {
    timestamps.push(eventItem.time?.getTime?.() || 0);
  });

  const normalized = timestamps.filter((item) => Number.isFinite(item) && item > 0);
  if (normalized.length === 0) {
    return null;
  }

  return {
    start: new Date(Math.min(...normalized)),
    end: new Date(Math.max(...normalized)),
  };
});
</script>

<template>
  <section class="rounded-card border border-stroke-soft bg-white p-3">
    <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
      <h4 class="text-sm font-semibold text-slate-800">LOT 生產 Timeline</h4>
      <div class="flex items-center gap-3 text-xs text-slate-500">
        <span v-if="timeRange">{{ formatDateTime(timeRange.start) }} — {{ formatDateTime(timeRange.end) }}</span>
        <span>Hold / Material 事件已覆蓋標記</span>
      </div>
    </div>

    <div v-if="tracks.length === 0" class="rounded-card border border-dashed border-stroke-soft bg-surface-muted/40 px-3 py-5 text-center text-xs text-slate-500">
      歷程資料不足，無法產生 Timeline
    </div>

    <div v-else class="max-h-[420px] overflow-y-auto rounded-card border border-stroke-soft">
      <TimelineChart
        :tracks="tracks"
        :events="events"
        :time-range="timeRange"
        :color-map="colorMap"
        :label-width="180"
        :track-row-height="46"
        :min-chart-width="1040"
      />
    </div>
  </section>
</template>
