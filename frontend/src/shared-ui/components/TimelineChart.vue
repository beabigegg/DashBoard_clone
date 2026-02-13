<script setup>
import { computed, ref } from 'vue';

import { formatDateTime, normalizeText, parseDateTime } from '../../query-tool/utils/values.js';

const props = defineProps({
  tracks: {
    type: Array,
    default: () => [],
  },
  events: {
    type: Array,
    default: () => [],
  },
  timeRange: {
    type: Object,
    default: null,
  },
  colorMap: {
    type: Object,
    default: () => ({}),
  },
  labelWidth: {
    type: Number,
    default: 200,
  },
  trackRowHeight: {
    type: Number,
    default: 44,
  },
  minChartWidth: {
    type: Number,
    default: 960,
  },
});

const AXIS_HEIGHT = 42;
const tooltipRef = ref({
  visible: false,
  x: 0,
  y: 0,
  title: '',
  lines: [],
});
const containerRef = ref(null);

function toTimestamp(value) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  const date = parseDateTime(value);
  return date ? date.getTime() : null;
}

function collectDomainTimestamps() {
  const timestamps = [];

  props.tracks.forEach((track) => {
    const layers = Array.isArray(track?.layers) ? track.layers : [];
    layers.forEach((layer) => {
      const bars = Array.isArray(layer?.bars) ? layer.bars : [];
      bars.forEach((bar) => {
        const startMs = toTimestamp(bar?.start);
        const endMs = toTimestamp(bar?.end);
        if (startMs !== null) timestamps.push(startMs);
        if (endMs !== null) timestamps.push(endMs);
      });
    });
  });

  props.events.forEach((event) => {
    const timeMs = toTimestamp(event?.time);
    if (timeMs !== null) timestamps.push(timeMs);
  });

  return timestamps;
}

const normalizedTimeRange = computed(() => {
  const explicitStart = toTimestamp(props.timeRange?.start);
  const explicitEnd = toTimestamp(props.timeRange?.end);

  if (explicitStart !== null && explicitEnd !== null && explicitEnd > explicitStart) {
    return {
      startMs: explicitStart,
      endMs: explicitEnd,
    };
  }

  const timestamps = collectDomainTimestamps();
  if (timestamps.length === 0) {
    const now = Date.now();
    return {
      startMs: now - (1000 * 60 * 60),
      endMs: now + (1000 * 60 * 60),
    };
  }

  const startMs = Math.min(...timestamps);
  const endMs = Math.max(...timestamps);
  if (endMs === startMs) {
    return {
      startMs,
      endMs: startMs + (1000 * 60 * 60),
    };
  }

  return {
    startMs,
    endMs,
  };
});

const totalDurationMs = computed(() => {
  return Math.max(1, normalizedTimeRange.value.endMs - normalizedTimeRange.value.startMs);
});

const trackCount = computed(() => props.tracks.length);

const chartWidth = computed(() => {
  const hours = totalDurationMs.value / (1000 * 60 * 60);
  const estimated = Math.round(hours * 36);
  return Math.max(props.minChartWidth, estimated);
});

const svgHeight = computed(() => AXIS_HEIGHT + trackCount.value * props.trackRowHeight + 2);

function rowTopByIndex(index) {
  return AXIS_HEIGHT + index * props.trackRowHeight;
}

function xByTimestamp(timestamp) {
  return ((timestamp - normalizedTimeRange.value.startMs) / totalDurationMs.value) * chartWidth.value;
}

function normalizeBar(bar) {
  const startMs = toTimestamp(bar?.start);
  const endMs = toTimestamp(bar?.end);
  if (startMs === null || endMs === null) {
    return null;
  }

  const safeEndMs = endMs > startMs ? endMs : startMs + (1000 * 60);
  return {
    ...bar,
    startMs,
    endMs: safeEndMs,
  };
}

function normalizeEvent(event) {
  const timeMs = toTimestamp(event?.time);
  if (timeMs === null) {
    return null;
  }
  return {
    ...event,
    timeMs,
  };
}

const timelineTicks = computed(() => {
  const ticks = [];
  const rangeMs = totalDurationMs.value;
  const rangeHours = rangeMs / (1000 * 60 * 60);

  const stepMs = rangeHours <= 48
    ? (1000 * 60 * 60)
    : (1000 * 60 * 60 * 24);

  const start = normalizedTimeRange.value.startMs;
  const end = normalizedTimeRange.value.endMs;

  let cursor = start;
  while (cursor <= end) {
    const date = new Date(cursor);
    const label = stepMs < (1000 * 60 * 60 * 24)
      ? `${String(date.getHours()).padStart(2, '0')}:00`
      : `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

    ticks.push({
      timeMs: cursor,
      label,
    });

    cursor += stepMs;
  }

  if (ticks.length < 2) {
    ticks.push({
      timeMs: end,
      label: stepMs < (1000 * 60 * 60 * 24) ? 'End' : '結束',
    });
  }

  return ticks;
});

const colorFallback = Object.freeze({
  default: '#94a3b8',
});

function resolveColor(type) {
  const key = normalizeText(type);
  if (key && props.colorMap[key]) {
    return props.colorMap[key];
  }
  return colorFallback.default;
}

function layerGeometry(trackIndex, layerIndex, layerCount) {
  const rowTop = rowTopByIndex(trackIndex);
  const maxBarHeight = Math.max(16, props.trackRowHeight - 14);
  const scale = layerCount <= 1
    ? 1
    : (layerIndex === 0 ? 1 : Math.max(0.4, 1 - layerIndex * 0.2));

  const height = maxBarHeight * scale;
  const y = rowTop + 6 + ((maxBarHeight - height) / 2);

  return {
    y,
    height,
  };
}

const legendItems = computed(() => {
  const usedTypes = new Set();

  props.tracks.forEach((track) => {
    const layers = Array.isArray(track?.layers) ? track.layers : [];
    layers.forEach((layer) => {
      const bars = Array.isArray(layer?.bars) ? layer.bars : [];
      bars.forEach((bar) => {
        const key = normalizeText(bar?.type);
        if (key) {
          usedTypes.add(key);
        }
      });
    });
  });

  props.events.forEach((event) => {
    const key = normalizeText(event?.type);
    if (key) {
      usedTypes.add(key);
    }
  });

  const keys = usedTypes.size > 0 ? [...usedTypes] : Object.keys(props.colorMap);
  return keys.map((key) => ({
    key,
    color: resolveColor(key),
  }));
});

function showTooltip(event, title, lines = []) {
  const host = containerRef.value;
  if (!host) {
    return;
  }

  const bounds = host.getBoundingClientRect();
  tooltipRef.value = {
    visible: true,
    x: event.clientX - bounds.left + 12,
    y: event.clientY - bounds.top + 12,
    title,
    lines,
  };
}

function hideTooltip() {
  tooltipRef.value.visible = false;
}

function handleBarHover(mouseEvent, bar, trackLabel) {
  const normalized = normalizeBar(bar);
  if (!normalized) {
    return;
  }

  const start = formatDateTime(normalized.start);
  const end = formatDateTime(normalized.end);
  const durationHours = ((normalized.endMs - normalized.startMs) / (1000 * 60 * 60)).toFixed(2);

  const title = normalizeText(normalized.label) || normalizeText(normalized.type) || '區段';
  const lines = [
    `Track: ${trackLabel}`,
    `Start: ${start}`,
    `End: ${end}`,
    `Duration: ${durationHours}h`,
    normalizeText(normalized.detail),
  ].filter(Boolean);

  showTooltip(mouseEvent, title, lines);
}

function handleEventHover(mouseEvent, eventItem, trackLabel) {
  const normalized = normalizeEvent(eventItem);
  if (!normalized) {
    return;
  }

  const title = normalizeText(normalized.label) || normalizeText(normalized.type) || '事件';
  const lines = [
    `Track: ${trackLabel}`,
    `Time: ${formatDateTime(normalized.time)}`,
    normalizeText(normalized.detail),
  ].filter(Boolean);

  showTooltip(mouseEvent, title, lines);
}

function eventPath(type, x, y) {
  const normalizedType = normalizeText(type).toLowerCase();

  if (normalizedType.includes('job') || normalizedType.includes('maint')) {
    return `M ${x} ${y - 7} L ${x - 7} ${y + 5} L ${x + 7} ${y + 5} Z`;
  }

  return `M ${x} ${y - 7} L ${x - 7} ${y} L ${x} ${y + 7} L ${x + 7} ${y} Z`;
}
</script>

<template>
  <div class="rounded-card border border-stroke-soft bg-white p-3">
    <div class="mb-3 flex flex-wrap items-center gap-3 text-xs text-slate-600">
      <span class="font-medium text-slate-700">Timeline</span>
      <div v-for="item in legendItems" :key="item.key" class="flex items-center gap-1">
        <span class="inline-block size-2 rounded-full" :style="{ backgroundColor: item.color }" />
        <span>{{ item.key }}</span>
      </div>
    </div>

    <div
      ref="containerRef"
      class="relative overflow-hidden rounded-card border border-stroke-soft bg-surface-muted/30"
      @mouseleave="hideTooltip"
    >
      <div class="grid" :style="{ gridTemplateColumns: `${labelWidth}px minmax(0, 1fr)` }">
        <div class="sticky left-0 z-20 border-r border-stroke-soft bg-white">
          <div class="flex h-[42px] items-center border-b border-stroke-soft px-3 text-xs font-semibold tracking-wide text-slate-500">
            Track
          </div>

          <div
            v-for="track in tracks"
            :key="track.id || track.label"
            class="flex items-center border-b border-stroke-soft/70 px-3 text-xs text-slate-700"
            :style="{ height: `${trackRowHeight}px` }"
          >
            <span class="line-clamp-1">{{ track.label }}</span>
          </div>
        </div>

        <div class="overflow-x-auto">
          <svg
            :width="chartWidth"
            :height="svgHeight"
            :viewBox="`0 0 ${chartWidth} ${svgHeight}`"
            class="block"
          >
            <rect x="0" y="0" :width="chartWidth" :height="svgHeight" fill="#ffffff" />

            <g>
              <line x1="0" :x2="chartWidth" y1="41" y2="41" stroke="#cbd5e1" stroke-width="1" />
              <g v-for="tick in timelineTicks" :key="tick.timeMs">
                <line
                  :x1="xByTimestamp(tick.timeMs)"
                  :x2="xByTimestamp(tick.timeMs)"
                  y1="0"
                  :y2="svgHeight"
                  stroke="#e2e8f0"
                  stroke-width="1"
                  stroke-dasharray="2 3"
                />
                <text
                  :x="xByTimestamp(tick.timeMs) + 2"
                  y="14"
                  fill="#475569"
                  font-size="11"
                >
                  {{ tick.label }}
                </text>
              </g>
            </g>

            <g v-for="(track, trackIndex) in tracks" :key="track.id || track.label">
              <rect
                x="0"
                :y="rowTopByIndex(trackIndex)"
                :width="chartWidth"
                :height="trackRowHeight"
                :fill="trackIndex % 2 === 0 ? '#f8fafc' : '#f1f5f9'"
                opacity="0.45"
              />

              <g v-for="(layer, layerIndex) in (track.layers || [])" :key="layer.id || layerIndex">
                <template
                  v-for="(bar, barIndex) in (layer.bars || [])"
                  :key="bar.id || `${trackIndex}-${layerIndex}-${barIndex}`"
                >
                  <rect
                    v-if="normalizeBar(bar)"
                    :x="xByTimestamp(normalizeBar(bar).startMs)"
                    :y="layerGeometry(trackIndex, layerIndex, (track.layers || []).length).y"
                    :width="Math.max(2, xByTimestamp(normalizeBar(bar).endMs) - xByTimestamp(normalizeBar(bar).startMs))"
                    :height="layerGeometry(trackIndex, layerIndex, (track.layers || []).length).height"
                    :fill="bar.color || resolveColor(bar.type)"
                    :opacity="layer.opacity ?? (layerIndex === 0 ? 0.45 : 0.9)"
                    rx="3"
                    @mousemove="handleBarHover($event, bar, track.label)"
                  />
                </template>
              </g>

              <template v-for="(eventItem, eventIndex) in events" :key="eventItem.id || `${trackIndex}-event-${eventIndex}`">
                <path
                  v-if="normalizeEvent(eventItem) && normalizeText(eventItem.trackId) === normalizeText(track.id)"
                  :d="eventPath(eventItem.shape || eventItem.type, xByTimestamp(normalizeEvent(eventItem).timeMs), rowTopByIndex(trackIndex) + (trackRowHeight / 2))"
                  :fill="eventItem.color || resolveColor(eventItem.type)"
                  stroke="#0f172a"
                  stroke-width="0.5"
                  @mousemove="handleEventHover($event, eventItem, track.label)"
                />
              </template>
            </g>
          </svg>
        </div>
      </div>

      <div
        v-if="tooltipRef.visible"
        class="pointer-events-none absolute z-30 max-w-72 rounded-card border border-stroke-soft bg-slate-900/95 px-2 py-1.5 text-[11px] text-slate-100 shadow-lg"
        :style="{ left: `${tooltipRef.x}px`, top: `${tooltipRef.y}px` }"
      >
        <p class="font-semibold text-white">{{ tooltipRef.title }}</p>
        <p v-for="line in tooltipRef.lines" :key="line" class="mt-0.5 text-slate-200">{{ line }}</p>
      </div>
    </div>
  </div>
</template>
