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

// ── Tracks: group by (WORKCENTER_GROUP × LOT ID × Equipment) ──
const tracks = computed(() => {
  const grouped = new Map();

  props.historyRows.forEach((row, index) => {
    const groupName = normalizeText(row?.WORKCENTER_GROUP)
      || normalizeText(row?.WORKCENTERNAME)
      || `WORKCENTER-${index + 1}`;
    const lotId = normalizeText(row?.CONTAINERNAME || row?.CONTAINERID) || '';
    const equipment = normalizeText(row?.EQUIPMENTNAME) || '';
    const trackKey = `${groupName}||${lotId}||${equipment}`;

    const start = safeDate(row?.TRACKINTIMESTAMP);
    const end = safeDate(row?.TRACKOUTTIMESTAMP) || (start ? new Date(start.getTime() + (1000 * 60 * 30)) : null);

    if (!start || !end) {
      return;
    }

    if (!grouped.has(trackKey)) {
      grouped.set(trackKey, { groupName, lotId, equipment, bars: [] });
    }

    grouped.get(trackKey).bars.push({
      id: `${trackKey}-${index}`,
      start,
      end,
      type: groupName,
      label: row?.SPECNAME || groupName,
    });
  });

  return [...grouped.entries()].map(([trackKey, { groupName, lotId, equipment, bars }]) => ({
    id: trackKey,
    group: groupName,
    label: groupName,
    sublabels: [
      lotId ? `LOT ID: ${lotId}` : '',
      equipment ? `機台編號: ${equipment}` : '',
    ].filter(Boolean),
    layers: [
      {
        id: `${trackKey}-lots`,
        bars,
        opacity: 0.85,
      },
    ],
  }));
});

// ── Events: resolve trackId to compound key via group matching ──
const groupToFirstTrackId = computed(() => {
  const map = new Map();
  tracks.value.forEach((track) => {
    if (!map.has(track.group)) {
      map.set(track.group, track.id);
    }
  });
  return map;
});

function resolveEventTrackId(row) {
  const group = normalizeText(row?.WORKCENTER_GROUP) || normalizeText(row?.WORKCENTERNAME) || '';
  return groupToFirstTrackId.value.get(group) || group;
}

const events = computed(() => {
  const markers = [];

  props.holdRows.forEach((row, index) => {
    const time = safeDate(row?.HOLDTXNDATE);
    if (!time) {
      return;
    }

    markers.push({
      id: `hold-${index}`,
      trackId: resolveEventTrackId(row),
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
      trackId: resolveEventTrackId(row),
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

  // Color by workcenter group (not compound key) so same group = same color
  const seen = new Set();
  tracks.value.forEach((track) => {
    if (!seen.has(track.group)) {
      seen.add(track.group);
      colors[track.group] = hashColor(track.group);
    }
  });

  return colors;
});

const timeRange = computed(() => {
  // Derive range ONLY from history bars so it updates when LOT selection
  // or workcenter group filter changes. Hold/material events are supplementary
  // markers and should not stretch the visible range.
  const timestamps = [];

  tracks.value.forEach((track) => {
    (track.layers || []).forEach((layer) => {
      (layer.bars || []).forEach((bar) => {
        timestamps.push(bar.start?.getTime?.() || 0);
        timestamps.push(bar.end?.getTime?.() || 0);
      });
    });
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

    <div v-else class="max-h-[520px] overflow-y-auto">
      <TimelineChart
        :tracks="tracks"
        :events="events"
        :time-range="timeRange"
        :color-map="colorMap"
        :label-width="200"
        :track-row-height="58"
        :min-chart-width="600"
      />
    </div>
  </section>
</template>
