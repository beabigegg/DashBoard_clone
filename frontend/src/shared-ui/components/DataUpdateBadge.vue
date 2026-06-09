<script setup lang="ts">
interface Props {
  updateTime?: string
  refreshing?: boolean
  refreshSuccess?: boolean
  refreshError?: boolean
}

withDefaults(defineProps<Props>(), {
  updateTime: '--',
  refreshing: false,
  refreshSuccess: false,
  refreshError: false,
})
</script>

<template>
  <span
    class="data-update-badge"
    :class="{
      'data-update-badge--refreshing': refreshing,
      'data-update-badge--success': refreshSuccess && !refreshing,
      'data-update-badge--error': refreshError && !refreshing,
    }"
    aria-live="polite"
    :aria-label="`資料更新時間：${updateTime}`"
  >
    <span class="data-update-badge__dot" aria-hidden="true">
      <span class="data-update-badge__dot-ring"></span>
    </span>
    <span class="data-update-badge__text">更新 <span class="data-update-badge__time">{{ updateTime }}</span></span>
  </span>
</template>

<style scoped>
.data-update-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px 3px 8px;
  border-radius: 9999px;
  border: 1px solid var(--border, #e2e8f0);
  background: var(--surface-card, #f8fafc);
  font-size: 11px;
  color: var(--muted, #64748b);
  white-space: nowrap;
  user-select: none;
  transition: border-color 0.3s ease, background 0.3s ease;
  vertical-align: middle;
}

.data-update-badge--refreshing {
  border-color: #86efac;
  background: #f0fdf4;
  color: #15803d;
}

.data-update-badge--success {
  border-color: #86efac;
  animation: badge-success-fade 1.8s ease-out forwards;
}

.data-update-badge--error {
  border-color: #fca5a5;
  color: #b91c1c;
}

/* Dot wrapper */
.data-update-badge__dot {
  position: relative;
  width: 7px;
  height: 7px;
  flex-shrink: 0;
}

/* Core dot */
.data-update-badge__dot::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: #cbd5e1;
  transition: background 0.3s ease;
}

/* Ripple ring (hidden by default) */
.data-update-badge__dot-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  opacity: 0;
  pointer-events: none;
}

/* Refreshing: pulsing dot + expanding ring */
.data-update-badge--refreshing .data-update-badge__dot::before {
  background: #22c55e;
  animation: badge-dot-pulse 1.4s ease-in-out infinite;
}

.data-update-badge--refreshing .data-update-badge__dot-ring {
  background: #22c55e;
  animation: badge-ripple 1.4s ease-out infinite;
}

/* Success: solid green */
.data-update-badge--success .data-update-badge__dot::before {
  background: #22c55e;
}

/* Error: red */
.data-update-badge--error .data-update-badge__dot::before {
  background: #ef4444;
}

.data-update-badge__text {
  letter-spacing: 0.01em;
}

.data-update-badge__time {
  font-variant-numeric: tabular-nums;
}

@keyframes badge-dot-pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.35; }
}

@keyframes badge-ripple {
  0%   { opacity: 0.5; transform: scale(1); }
  100% { opacity: 0;   transform: scale(3); }
}

@keyframes badge-success-fade {
  0%, 60% { border-color: #86efac; }
  100%     { border-color: var(--border, #e2e8f0); }
}
</style>
