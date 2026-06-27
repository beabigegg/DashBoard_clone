<script setup lang="ts">
import { computed } from 'vue';

import TimelineChart from '../../shared-ui/components/TimelineChart.vue';
import { formatDateTime, hashColor, normalizeText, parseDateTime } from '../utils/values';

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
  pagination: {
    type: Object,
    default: null,
  },
});

const isTruncated = computed(() => {
  if (!props.pagination) return false;
  const { total, per_page } = props.pagination as { total?: number; per_page?: number };
  return (total ?? 0) > (per_page ?? 0);
});

function safeDate(value: unknown): Date | null {
  const parsed = parseDateTime(value);
  return parsed ? parsed : null;
}

function normalizedKey(value: unknown): string {
  return normalizeText(value).toUpperCase();
}

// ── Tracks: group by (WORKCENTER_GROUP × LOT ID × Equipment) ──
const tracks = computed(() => {
  const grouped = new Map();

  props.historyRows.forEach((rawRow, index) => {
    const row = rawRow as Record<string, unknown>;
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
        containerId: normalizeText(row.CONTAINERID),
        bars: [],
      });
    }

    grouped.get(trackKey).bars.push({
      id: `${trackKey}-${index}`,
      start,
      end,
      type: groupName,
      label: normalizeText(row?.SPECNAME) || groupName,
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
      (layer.bars || []).forEach((bar: { start?: Date; end?: Date; label?: string; type?: string }) => {
        const specKey = normalizedKey(bar?.label || bar?.type);
        const startMs = bar?.start instanceof Date ? bar.start.getTime() : null;
        const endMs = bar?.end instanceof Date ? bar.end.getTime() : null;
        if (startMs === null || endMs === null || !specKey) {
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

function pickClosestTrack(windows: Array<{ trackId: string; startMs: number; endMs: number }>, timeMs: number | null): string {
  if (!Array.isArray(windows) || windows.length === 0) {
    return '';
  }
  if (timeMs === null || !Number.isFinite(timeMs)) {
    return windows[0]?.trackId || '';
  }
  const t: number = timeMs;

  let best = '';
  let bestDistance = Number.POSITIVE_INFINITY;
  windows.forEach((window) => {
    if (!window?.trackId) {
      return;
    }
    if (t >= window.startMs && t <= window.endMs) {
      if (0 < bestDistance) {
        best = window.trackId;
        bestDistance = 0;
      }
      return;
    }
    const distance = t < window.startMs
      ? (window.startMs - t)
      : (t - window.endMs);
    if (distance < bestDistance) {
      best = window.trackId;
      bestDistance = distance;
    }
  });

  return best;
}

function resolveHoldTrackId(row: Record<string, unknown>): string {
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

function resolveMaterialTrackId(row: Record<string, unknown>, time: Date | null): string {
  const specKey = normalizedKey(row?.SPECNAME);
  const containerKey = normalizedKey(row?.CONTAINERID);
  if (!specKey || !containerKey) {
    return '';
  }

  const windows = containerSpecWindows.value.get(`${containerKey}||${specKey}`) || [];
  const timeMs = time instanceof Date ? time.getTime() : null;
  return pickClosestTrack(windows, timeMs);
}

interface LocalTimelineEvent {
  id: string;
  trackId: string;
  time: number;
  type: string;
  shape: string;
  label: string;
  detail: string;
}

const events = computed(() => {
  const markers: LocalTimelineEvent[] = [];

  props.holdRows.forEach((rawRow, index) => {
    const row = rawRow as Record<string, unknown>;
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
      time: time.getTime(),
      type: 'HOLD',
      shape: 'diamond',
      label: 'Hold',
      detail: `${normalizeText(row?.HOLDREASONNAME)} ${normalizeText(row?.HOLDCOMMENTS)}`.trim(),
    });
  });

  props.materialRows.forEach((rawRow, index) => {
    const row = rawRow as Record<string, unknown>;
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
      time: time.getTime(),
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

  props.materialRows.forEach((rawRow) => {
    const row = rawRow as Record<string, unknown>;
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
  const colors: Record<string, string> = {
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
  const timestamps: number[] = [];

  tracks.value.forEach((track) => {
    (track.layers || []).forEach((layer) => {
      (layer.bars || []).forEach((bar: { start?: Date; end?: Date }) => {
        timestamps.push(bar.start?.getTime?.() || 0);
        timestamps.push(bar.end?.getTime?.() || 0);
      });
    });
  });

  const normalized = timestamps.filter((item) => Number.isFinite(item) && item > 0);
  if (normalized.length === 0) {
    return null;
  }

  // Return as numbers (ms) so TimelineChart's TimeRange { start?: string|number } is satisfied
  return {
    start: Math.min(...normalized),
    end: Math.max(...normalized),
  };
});
</script>

<template>
  <div class="lot-tl-wrap">
    <!-- Meta row -->
    <div class="lot-tl-meta">
      <span v-if="timeRange" class="lot-tl-meta-range">
        {{ formatDateTime(timeRange.start) }} — {{ formatDateTime(timeRange.end) }}
      </span>
      <div class="lot-tl-meta-badges">
        <span class="lot-tl-badge lot-tl-badge--info">
          <span class="lot-tl-badge-dot lot-tl-badge-dot--hold" />
          Hold / Material 事件已覆蓋標記
        </span>
        <span
          v-if="materialMappingStats.total > 0"
          class="lot-tl-badge"
          :class="materialMappingStats.unmapped > 0 ? 'lot-tl-badge--warn' : 'lot-tl-badge--ok'"
        >
          扣料對應 {{ materialMappingStats.mapped }} / {{ materialMappingStats.total }}
          <template v-if="materialMappingStats.unmapped > 0">（未對應 {{ materialMappingStats.unmapped }}）</template>
        </span>
      </div>
    </div>

    <div v-if="isTruncated" class="query-tool-warning">
      ⚠️ Timeline 目前僅顯示前 {{ pagination?.per_page }} 筆資料（共 {{ pagination?.total }} 筆），部分 LOT 可能未顯示。請至下方歷程表格調大每頁筆數，或依站點篩選縮小範圍。
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
        :track-row-height="56"
        :min-chart-width="600"
      />
    </div>
  </div>
</template>

<style scoped>
.lot-tl-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lot-tl-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.lot-tl-meta-range {
  font-size: 11.5px;
  font-family: ui-monospace, monospace;
  color: theme('colors.text.secondary');
  font-weight: 500;
}

.lot-tl-meta-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.lot-tl-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
  background: theme('colors.surface.hover');
  color: theme('colors.text.subtle');
  border: 1px solid theme('colors.stroke.soft');
}

.lot-tl-badge--info { background: theme('colors.sky.50'); color: theme('colors.sky.700'); border-color: theme('colors.sky.200'); }
.lot-tl-badge--ok   { background: theme('colors.token.hf0fdf4'); color: theme('colors.token.h166534'); border-color: theme('colors.token.hbbf7d0'); }
.lot-tl-badge--warn { background: theme('colors.token.hfffbeb'); color: theme('colors.token.h92400e'); border-color: theme('colors.token.hfde68a'); }

.lot-tl-badge-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
  flex-shrink: 0;
}
.lot-tl-badge-dot--hold { background: theme('colors.state.warning'); }

.timeline-scroll-area {
  max-height: 520px;
  overflow-y: auto;
}
</style>
