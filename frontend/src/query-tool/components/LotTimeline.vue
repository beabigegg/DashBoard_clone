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

function normalizedKey(value) {
  return normalizeText(value).toUpperCase();
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
      grouped.set(trackKey, {
        groupName,
        lotId,
        equipment,
        containerId: normalizeText(row?.CONTAINERID),
        bars: [],
      });
    }

    grouped.get(trackKey).bars.push({
      id: `${trackKey}-${index}`,
      start,
      end,
      type: groupName,
      label: row?.SPECNAME || groupName,
    });
  });

  return [...grouped.entries()].map(([trackKey, { groupName, lotId, equipment, containerId, bars }]) => ({
    id: trackKey,
    group: groupName,
    containerId,
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

// ── Events: resolve event-to-track mapping ──
const groupToFirstTrackId = computed(() => {
  const map = new Map();
  tracks.value.forEach((track) => {
    const key = normalizedKey(track.group);
    if (key && !map.has(key)) {
      map.set(key, track.id);
    }
  });
  return map;
});

const containerToTrackIds = computed(() => {
  const map = new Map();
  tracks.value.forEach((track) => {
    const cid = normalizedKey(track.containerId);
    if (!cid) {
      return;
    }
    if (!map.has(cid)) {
      map.set(cid, []);
    }
    map.get(cid).push(track.id);
  });
  return map;
});

const containerSpecWindows = computed(() => {
  const map = new Map();
  tracks.value.forEach((track) => {
    const containerKey = normalizedKey(track.containerId);
    if (!containerKey) {
      return;
    }
    (track.layers || []).forEach((layer) => {
      (layer.bars || []).forEach((bar) => {
        const specKey = normalizedKey(bar?.label || bar?.type);
        const startMs = bar?.start instanceof Date ? bar.start.getTime() : null;
        const endMs = bar?.end instanceof Date ? bar.end.getTime() : null;
        if (!specKey || !Number.isFinite(startMs) || !Number.isFinite(endMs)) {
          return;
        }

        const key = `${containerKey}||${specKey}`;
        if (!map.has(key)) {
          map.set(key, []);
        }

        map.get(key).push({
          trackId: track.id,
          startMs,
          endMs: endMs > startMs ? endMs : startMs,
        });
      });
    });
  });
  return map;
});

function pickClosestTrack(windows, timeMs) {
  if (!Array.isArray(windows) || windows.length === 0) {
    return '';
  }
  if (!Number.isFinite(timeMs)) {
    return windows[0]?.trackId || '';
  }

  let best = '';
  let bestDistance = Number.POSITIVE_INFINITY;
  windows.forEach((window) => {
    if (!window?.trackId) {
      return;
    }
    if (timeMs >= window.startMs && timeMs <= window.endMs) {
      if (0 < bestDistance) {
        best = window.trackId;
        bestDistance = 0;
      }
      return;
    }
    const distance = timeMs < window.startMs
      ? (window.startMs - timeMs)
      : (timeMs - window.endMs);
    if (distance < bestDistance) {
      best = window.trackId;
      bestDistance = distance;
    }
  });

  return best;
}

function resolveHoldTrackId(row) {
  const groupKey = normalizedKey(row?.WORKCENTER_GROUP) || normalizedKey(row?.WORKCENTERNAME);
  if (groupKey) {
    const trackId = groupToFirstTrackId.value.get(groupKey);
    if (trackId) {
      return trackId;
    }
  }

  const containerKey = normalizedKey(row?.CONTAINERID);
  if (containerKey) {
    const byContainer = containerToTrackIds.value.get(containerKey) || [];
    if (byContainer.length > 0) {
      return byContainer[0];
    }
  }

  return '';
}

function resolveMaterialTrackId(row, time) {
  const specKey = normalizedKey(row?.SPECNAME);
  const containerKey = normalizedKey(row?.CONTAINERID);
  if (!specKey || !containerKey) {
    return '';
  }

  const windows = containerSpecWindows.value.get(`${containerKey}||${specKey}`) || [];
  const timeMs = time instanceof Date ? time.getTime() : null;
  return pickClosestTrack(windows, timeMs);
}

const events = computed(() => {
  const markers = [];

  props.holdRows.forEach((row, index) => {
    const time = safeDate(row?.HOLDTXNDATE);
    if (!time) {
      return;
    }
    const trackId = resolveHoldTrackId(row);
    if (!trackId) {
      return;
    }

    markers.push({
      id: `hold-${index}`,
      trackId,
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
    const trackId = resolveMaterialTrackId(row, time);
    if (!trackId) {
      return;
    }

    markers.push({
      id: `material-${index}`,
      trackId,
      time,
      type: 'MATERIAL',
      shape: 'triangle',
      label: normalizeText(row?.MATERIALPARTNAME) || 'Material',
      detail: `Qty ${row?.QTYCONSUMED ?? '-'} / ${normalizeText(row?.MATERIALLOTNAME)}`,
    });
  });

  return markers;
});

const materialMappingStats = computed(() => {
  let total = 0;
  let mapped = 0;

  props.materialRows.forEach((row) => {
    const time = safeDate(row?.TXNDATE);
    if (!time) {
      return;
    }
    total += 1;
    if (resolveMaterialTrackId(row, time)) {
      mapped += 1;
    }
  });

  return {
    total,
    mapped,
    unmapped: Math.max(0, total - mapped),
  };
});

const colorMap = computed(() => {
  const colors = {
    HOLD: 'var(--color-token-hf59e0b)',
    MATERIAL: 'var(--color-token-h0ea5e9)',
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
  <div>
    <div class="query-tool-section-header">
      <h4 class="card-title ui-card-title">LOT 生產 Timeline</h4>
      <div class="flex items-center gap-3 query-tool-muted">
        <span v-if="timeRange">{{ formatDateTime(timeRange.start) }} — {{ formatDateTime(timeRange.end) }}</span>
        <span>Hold / Material 事件已覆蓋標記</span>
        <span v-if="materialMappingStats.total > 0">
          扣料對應 {{ materialMappingStats.mapped }} / {{ materialMappingStats.total }}
          <template v-if="materialMappingStats.unmapped > 0">
            （未對應 {{ materialMappingStats.unmapped }}）
          </template>
        </span>
      </div>
    </div>

    <div v-if="tracks.length === 0" class="placeholder">
      歷程資料不足，無法產生 Timeline
    </div>

    <div v-else class="timeline-scroll-area">
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
  </div>
</template>

<style scoped>
.timeline-scroll-area {
  max-height: 520px;
  overflow-y: auto;
}
</style>
