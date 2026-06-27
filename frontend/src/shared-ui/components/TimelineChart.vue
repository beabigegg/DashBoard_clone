<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { formatDateTime, normalizeText, parseDateTime } from '../../query-tool/utils/values';

interface TimelineBar {
  id?: string;
  start: string | number;
  end: string | number;
  type?: string;
  label?: string;
  detail?: string;
  color?: string;
}

interface TimelineLayer {
  id?: string;
  bars?: TimelineBar[];
  opacity?: number;
}

interface TimelineTrack {
  id?: string;
  label?: string;
  sublabel?: string;
  sublabels?: string[];
  layers?: TimelineLayer[];
}

interface TimelineEvent {
  id?: string;
  time: string | number;
  type?: string;
  shape?: string;
  label?: string;
  detail?: string;
  color?: string;
  trackId?: string;
}

interface TimeRange {
  start?: string | number;
  end?: string | number;
}

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  title: string;
  lines: string[];
}

interface Props {
  tracks?: TimelineTrack[];
  events?: TimelineEvent[];
  timeRange?: TimeRange | null;
  colorMap?: Record<string, string>;
  labelWidth?: number;
  trackRowHeight?: number;
  minChartWidth?: number;
}

const props = withDefaults(defineProps<Props>(), {
  tracks: () => [],
  events: () => [],
  timeRange: null,
  colorMap: () => ({}),
  labelWidth: 200,
  trackRowHeight: 44,
  minChartWidth: 600,
});

const AXIS_HEIGHT = 32;
const RANGE_PAD_RATIO = 0.03;

const tooltipRef = ref<TooltipState>({
  visible: false,
  x: 0,
  y: 0,
  title: '',
  lines: [],
});
const containerRef = ref<HTMLElement | null>(null);
const scrollRef = ref<HTMLElement | null>(null);

function toTimestamp(value: string | number | null | undefined): number | null {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  const date = parseDateTime(value) as Date | null;
  return date ? date.getTime() : null;
}

function collectDomainTimestamps(): number[] {
  const timestamps: number[] = [];

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

  let startMs: number;
  let endMs: number;

  if (explicitStart !== null && explicitEnd !== null && explicitEnd > explicitStart) {
    startMs = explicitStart;
    endMs = explicitEnd;
  } else {
    const timestamps = collectDomainTimestamps();
    if (timestamps.length === 0) {
      const now = Date.now();
      return {
        startMs: now - (1000 * 60 * 60),
        endMs: now + (1000 * 60 * 60),
      };
    }

    startMs = Math.min(...timestamps);
    endMs = Math.max(...timestamps);
    if (endMs === startMs) {
      endMs = startMs + (1000 * 60 * 60);
    }
  }

  // Add a small padding so bars don't sit at the very edge
  const span = endMs - startMs;
  const pad = span * RANGE_PAD_RATIO;
  return {
    startMs: startMs - pad,
    endMs: endMs + pad,
  };
});

const totalDurationMs = computed(() => {
  return Math.max(1, normalizedTimeRange.value.endMs - normalizedTimeRange.value.startMs);
});

const trackCount = computed(() => props.tracks.length);

const chartWidth = computed(() => {
  const hours = totalDurationMs.value / (1000 * 60 * 60);
  // Adaptive scaling: longer durations get fewer px/hour to stay compact
  let pxPerHour: number;
  if (hours <= 6) pxPerHour = 120;
  else if (hours <= 24) pxPerHour = 60;
  else if (hours <= 72) pxPerHour = 30;
  else if (hours <= 168) pxPerHour = 16;
  else if (hours <= 720) pxPerHour = 6;
  else pxPerHour = 3;

  return Math.max(props.minChartWidth, Math.round(hours * pxPerHour));
});

const svgHeight = computed(() => AXIS_HEIGHT + trackCount.value * props.trackRowHeight + 2);

function rowTopByIndex(index: number): number {
  return AXIS_HEIGHT + index * props.trackRowHeight;
}

function xByTimestamp(timestamp: number): number {
  return ((timestamp - normalizedTimeRange.value.startMs) / totalDurationMs.value) * chartWidth.value;
}

interface NormalizedBar extends TimelineBar {
  startMs: number;
  endMs: number;
}

function normalizeBar(bar: TimelineBar): NormalizedBar | null {
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

interface NormalizedEvent extends TimelineEvent {
  timeMs: number;
}

function normalizeEvent(event: TimelineEvent): NormalizedEvent | null {
  const timeMs = toTimestamp(event?.time);
  if (timeMs === null) {
    return null;
  }
  return {
    ...event,
    timeMs,
  };
}

const HOUR_MS = 1000 * 60 * 60;
const DAY_MS = HOUR_MS * 24;

const timelineTicks = computed(() => {
  const ticks: { timeMs: number; label: string }[] = [];
  const rangeMs = totalDurationMs.value;
  const rangeHours = rangeMs / HOUR_MS;

  let stepMs: number;
  if (rangeHours <= 12) stepMs = HOUR_MS;
  else if (rangeHours <= 48) stepMs = HOUR_MS * 2;
  else if (rangeHours <= 168) stepMs = HOUR_MS * 6;
  else if (rangeHours <= 720) stepMs = DAY_MS;
  else stepMs = DAY_MS * 3;

  const start = normalizedTimeRange.value.startMs;
  const end = normalizedTimeRange.value.endMs;

  // Snap cursor to the nearest clean boundary
  const snapMs = stepMs >= DAY_MS ? DAY_MS : HOUR_MS;
  let cursor = Math.ceil(start / snapMs) * snapMs;

  while (cursor <= end) {
    const date = new Date(cursor);
    let label: string;
    if (stepMs < DAY_MS) {
      label = `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:00`;
    } else {
      label = `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    }

    ticks.push({ timeMs: cursor, label });
    cursor += stepMs;
  }

  if (ticks.length < 2) {
    ticks.push({
      timeMs: end,
      label: '結束',
    });
  }

  return ticks;
});

const colorFallback = Object.freeze({
  default: 'var(--color-token-h94a3b8)',
});

function resolveColor(type: string | undefined): string {
  const key = normalizeText(type) as string;
  if (key && props.colorMap[key]) {
    return props.colorMap[key];
  }
  return colorFallback.default;
}

function layerGeometry(trackIndex: number, layerIndex: number, layerCount: number): { y: number; height: number } {
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
  const usedTypes = new Set<string>();

  props.tracks.forEach((track) => {
    const layers = Array.isArray(track?.layers) ? track.layers : [];
    layers.forEach((layer) => {
      const bars = Array.isArray(layer?.bars) ? layer.bars : [];
      bars.forEach((bar) => {
        const key = normalizeText(bar?.type) as string;
        if (key) {
          usedTypes.add(key);
        }
      });
    });
  });

  props.events.forEach((event) => {
    const key = normalizeText(event?.type) as string;
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

// ── Tooltip (fixed-position, teleported to body) ──────────────
const TOOLTIP_MAX_W = 288; // max-w-72
const TOOLTIP_EST_H = 120;

function showTooltip(event: MouseEvent, title: string, lines: string[] = []) {
  let x = event.clientX + 14;
  let y = event.clientY + 14;

  // Flip when near viewport edges
  if (x + TOOLTIP_MAX_W > window.innerWidth - 8) {
    x = event.clientX - TOOLTIP_MAX_W - 8;
  }
  if (y + TOOLTIP_EST_H > window.innerHeight - 8) {
    y = event.clientY - TOOLTIP_EST_H - 8;
  }

  tooltipRef.value = {
    visible: true,
    x: Math.max(4, x),
    y: Math.max(4, y),
    title,
    lines,
  };
}

function hideTooltip() {
  tooltipRef.value.visible = false;
}

// Hide tooltip when the chart area scrolls (fixed tooltip would become stale)
function handleScroll() {
  if (tooltipRef.value.visible) {
    hideTooltip();
  }
}

onMounted(() => {
  scrollRef.value?.addEventListener('scroll', handleScroll, { passive: true });
});
onBeforeUnmount(() => {
  scrollRef.value?.removeEventListener('scroll', handleScroll);
  hideTooltip();
});

function handleBarHover(mouseEvent: MouseEvent, bar: TimelineBar, trackLabel: string | undefined) {
  const normalized = normalizeBar(bar);
  if (!normalized) {
    return;
  }

  const start = formatDateTime(normalized.start) as string;
  const end = formatDateTime(normalized.end) as string;
  const durationHours = ((normalized.endMs - normalized.startMs) / HOUR_MS).toFixed(2);

  const title = (normalizeText(normalized.label) || normalizeText(normalized.type) || '區段') as string;
  const lines = [
    `Track: ${trackLabel}`,
    `Start: ${start}`,
    `End: ${end}`,
    `Duration: ${durationHours}h`,
    normalizeText(normalized.detail) as string,
  ].filter(Boolean) as string[];

  showTooltip(mouseEvent, title, lines);
}

function handleEventHover(mouseEvent: MouseEvent, eventItem: TimelineEvent, trackLabel: string | undefined) {
  const normalized = normalizeEvent(eventItem);
  if (!normalized) {
    return;
  }

  const title = (normalizeText(normalized.label) || normalizeText(normalized.type) || '事件') as string;
  const lines = [
    `Track: ${trackLabel}`,
    `Time: ${formatDateTime(normalized.time) as string}`,
    normalizeText(normalized.detail) as string,
  ].filter(Boolean) as string[];

  showTooltip(mouseEvent, title, lines);
}

function eventPath(type: string | undefined, x: number, y: number): string {
  const normalizedType = (normalizeText(type) as string).toLowerCase();

  if (normalizedType.includes('job') || normalizedType.includes('maint')) {
    // upward triangle — slightly larger
    return `M ${x} ${y - 9} L ${x - 8} ${y + 6} L ${x + 8} ${y + 6} Z`;
  }

  // diamond — slightly larger
  return `M ${x} ${y - 9} L ${x - 8} ${y} L ${x} ${y + 9} L ${x + 8} ${y} Z`;
}
</script>

<template>
  <div class="tl-root">
    <!-- Legend -->
    <div class="tl-legend">
      <div v-for="item in legendItems" :key="item.key" class="tl-legend-item">
        <span
          class="tl-legend-swatch"
          :style="{ backgroundColor: item.color }"
        />
        <span>{{ item.key }}</span>
      </div>
    </div>

    <div
      ref="containerRef"
      class="tl-grid-wrap"
      @mouseleave="hideTooltip"
    >
      <div class="tl-grid" :style="{ gridTemplateColumns: `${labelWidth}px minmax(0, 1fr)` }">
        <!-- Track labels (sticky left) -->
        <div class="tl-labels">
          <div class="tl-label-header" :style="{ height: `${AXIS_HEIGHT}px` }">
            Station
          </div>

          <div
            v-for="(track, trackIndex) in tracks"
            :key="track.id || track.label"
            class="tl-label-row"
            :class="{ 'tl-label-row--even': trackIndex % 2 === 0 }"
            :style="{ height: `${trackRowHeight}px` }"
          >
            <span
              class="tl-label-stripe"
              :style="{ backgroundColor: resolveColor(track.label) }"
            />
            <div class="tl-label-text">
              <span class="tl-label-main">{{ track.label }}</span>
              <template v-if="track.sublabels?.length">
                <span v-for="sub in track.sublabels" :key="sub" class="tl-label-sub">{{ sub }}</span>
              </template>
              <span v-else-if="track.sublabel" class="tl-label-sub">{{ track.sublabel }}</span>
            </div>
          </div>
        </div>

        <!-- Chart area (scrollable) -->
        <div ref="scrollRef" class="tl-scroll">
          <svg
            :width="chartWidth"
            :height="svgHeight"
            :viewBox="`0 0 ${chartWidth} ${svgHeight}`"
            class="block"
          >
            <defs>
              <!-- Universal bar gloss overlay -->
              <linearGradient id="tl-bar-gloss" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="white" stop-opacity="0.28"/>
                <stop offset="50%" stop-color="white" stop-opacity="0.04"/>
                <stop offset="100%" stop-color="black" stop-opacity="0.06"/>
              </linearGradient>
            </defs>

            <rect x="0" y="0" :width="chartWidth" :height="svgHeight" fill="#ffffff" />

            <!-- Time axis -->
            <g>
              <rect x="0" y="0" :width="chartWidth" :height="AXIS_HEIGHT" fill="#f8fafc" />
              <line x1="0" :x2="chartWidth" :y1="AXIS_HEIGHT - 1" :y2="AXIS_HEIGHT - 1" stroke="#cbd5e1" stroke-width="1" />
              <g v-for="tick in timelineTicks" :key="tick.timeMs">
                <line
                  :x1="xByTimestamp(tick.timeMs)"
                  :x2="xByTimestamp(tick.timeMs)"
                  y1="0"
                  :y2="svgHeight"
                  stroke="#e2e8f0"
                  stroke-width="1"
                  stroke-dasharray="3 4"
                />
                <text
                  :x="xByTimestamp(tick.timeMs) + 4"
                  y="15"
                  fill="#64748b"
                  font-size="10.5"
                  font-weight="500"
                  font-family="ui-monospace, monospace"
                >
                  {{ tick.label }}
                </text>
              </g>
            </g>

            <!-- Track rows -->
            <g v-for="(track, trackIndex) in tracks" :key="track.id || track.label">
              <!-- Alternating row bg -->
              <rect
                x="0"
                :y="rowTopByIndex(trackIndex)"
                :width="chartWidth"
                :height="trackRowHeight"
                :fill="trackIndex % 2 === 0 ? '#f8fafc' : '#f1f5f9'"
              />
              <!-- Bottom row separator -->
              <line
                x1="0"
                :x2="chartWidth"
                :y1="rowTopByIndex(trackIndex) + trackRowHeight - 1"
                :y2="rowTopByIndex(trackIndex) + trackRowHeight - 1"
                stroke="#e2e8f0"
                stroke-width="1"
              />

              <!-- Bars -->
              <g v-for="(layer, layerIndex) in (track.layers || [])" :key="layer.id || layerIndex">
                <template
                  v-for="(bar, barIndex) in (layer.bars || [])"
                  :key="bar.id || `${trackIndex}-${layerIndex}-${barIndex}`"
                >
                  <template v-if="normalizeBar(bar)">
                    <!-- Bar base color -->
                    <rect
                      :x="xByTimestamp(normalizeBar(bar)!.startMs)"
                      :y="layerGeometry(trackIndex, layerIndex, (track.layers || []).length).y"
                      :width="Math.max(6, xByTimestamp(normalizeBar(bar)!.endMs) - xByTimestamp(normalizeBar(bar)!.startMs))"
                      :height="layerGeometry(trackIndex, layerIndex, (track.layers || []).length).height"
                      :fill="bar.color || resolveColor(bar.type)"
                      :opacity="layer.opacity ?? 0.92"
                      rx="4"
                      class="cursor-pointer"
                      @mousemove="handleBarHover($event, bar, track.label)"
                    />
                    <!-- Gloss overlay -->
                    <rect
                      :x="xByTimestamp(normalizeBar(bar)!.startMs)"
                      :y="layerGeometry(trackIndex, layerIndex, (track.layers || []).length).y"
                      :width="Math.max(6, xByTimestamp(normalizeBar(bar)!.endMs) - xByTimestamp(normalizeBar(bar)!.startMs))"
                      :height="layerGeometry(trackIndex, layerIndex, (track.layers || []).length).height"
                      fill="url(#tl-bar-gloss)"
                      rx="4"
                      style="pointer-events: none;"
                    />
                  </template>
                </template>
              </g>

              <!-- Event markers -->
              <template v-for="(eventItem, eventIndex) in events" :key="eventItem.id || `${trackIndex}-event-${eventIndex}`">
                <path
                  v-if="normalizeEvent(eventItem) && normalizeText(eventItem.trackId) === normalizeText(track.id)"
                  :d="eventPath(eventItem.shape || eventItem.type, xByTimestamp(normalizeEvent(eventItem)!.timeMs), rowTopByIndex(trackIndex) + (trackRowHeight / 2))"
                  :fill="eventItem.color || resolveColor(eventItem.type)"
                  stroke="white"
                  stroke-width="1.5"
                  stroke-linejoin="round"
                  class="cursor-pointer"
                  filter="drop-shadow(0 1px 2px rgba(0,0,0,0.25))"
                  @mousemove="handleEventHover($event, eventItem, track.label)"
                />
              </template>
            </g>
          </svg>
        </div>
      </div>
    </div>

    <!-- Tooltip: teleported to body so it's never clipped by overflow -->
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div
          v-if="tooltipRef.visible"
          class="tl-tooltip"
          :style="{ left: `${tooltipRef.x}px`, top: `${tooltipRef.y}px` }"
        >
          <p class="tl-tooltip-title">{{ tooltipRef.title }}</p>
          <p v-for="line in tooltipRef.lines" :key="line" class="tl-tooltip-line">{{ line }}</p>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* Root */
.tl-root {
  padding: 12px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

/* Legend */
.tl-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-bottom: 12px;
}
.tl-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: #475569;
  font-weight: 500;
}
.tl-legend-swatch {
  display: inline-block;
  width: 20px;
  height: 10px;
  border-radius: 3px;
  opacity: 0.9;
  flex-shrink: 0;
}

/* Grid wrapper */
.tl-grid-wrap {
  position: relative;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}
.tl-grid {
  display: grid;
}

/* Labels column */
.tl-labels {
  position: sticky;
  left: 0;
  z-index: 20;
  border-right: 1px solid #e2e8f0;
  background: #fff;
  box-shadow: 2px 0 8px rgba(0,0,0,0.06);
}
.tl-label-header {
  display: flex;
  align-items: center;
  padding: 0 12px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #94a3b8;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.tl-label-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid #e2e8f0;
}
.tl-label-row--even {
  background: #f8fafc;
}
.tl-label-stripe {
  flex-shrink: 0;
  width: 3px;
  align-self: stretch;
  opacity: 0.7;
}
.tl-label-text {
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 10px;
  overflow: hidden;
  min-width: 0;
}
.tl-label-main {
  font-size: 11.5px;
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tl-label-sub {
  font-size: 10px;
  line-height: 1.3;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Chart scroll area */
.tl-scroll {
  overflow-x: auto;
}

/* Tooltip */
.tl-tooltip {
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  max-width: 280px;
  padding: 10px 14px;
  border-radius: 10px;
  background: #1e293b;
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.50), 0 2px 8px rgba(0, 0, 0, 0.30);
  font-size: 11.5px;
  line-height: 1.6;
  color: #e2e8f0;
}
.tl-tooltip-title {
  font-weight: 600;
  color: #fff;
  margin-bottom: 4px;
}
.tl-tooltip-line {
  color: #94a3b8;
  margin-top: 2px;
}

/* Tooltip transitions */
.tooltip-fade-enter-active { transition: opacity 0.12s ease-out; }
.tooltip-fade-leave-active { transition: opacity 0.08s ease-in; }
.tooltip-fade-enter-from,
.tooltip-fade-leave-to { opacity: 0; }
</style>
