<script setup>
import { computed } from 'vue';

const props = defineProps({
  current_stage: {
    type: String,
    default: null,
  },
  completed_stages: {
    type: Array,
    default: () => [],
  },
  stage_errors: {
    type: Object,
    default: () => ({}),
  },
});

const STAGES = Object.freeze([
  { id: 'seed-resolve', key: 'seed', label: '批次解析' },
  { id: 'lineage', key: 'lineage', label: '血緣追溯' },
  { id: 'events', key: 'events', label: '事件查詢' },
]);

const completedSet = computed(() => new Set(props.completed_stages || []));

function hasStageError(stage) {
  const error = props.stage_errors?.[stage.key];
  return Boolean(error?.message || error?.code);
}

function stageState(stage) {
  if (hasStageError(stage)) {
    return 'error';
  }
  if (completedSet.value.has(stage.id)) {
    return 'complete';
  }
  if (props.current_stage === stage.id) {
    return 'active';
  }
  return 'pending';
}

const firstError = computed(() => {
  for (const stage of STAGES) {
    const error = props.stage_errors?.[stage.key];
    if (error?.message) {
      return `[${stage.label}] ${error.message}`;
    }
  }
  return '';
});
</script>

<template>
  <div class="trace-progress">
    <div class="trace-progress-track">
      <div
        v-for="(stage, index) in STAGES"
        :key="stage.id"
        class="trace-progress-step"
        :class="`is-${stageState(stage)}`"
      >
        <div class="trace-progress-dot"></div>
        <span class="trace-progress-label">{{ stage.label }}</span>
        <div v-if="index < STAGES.length - 1" class="trace-progress-line"></div>
      </div>
    </div>
    <p v-if="firstError" class="trace-progress-error">{{ firstError }}</p>
  </div>
</template>

<style scoped>
.trace-progress {
  margin: 12px 0 16px;
  padding: 12px 14px;
  border: 1px solid #dbeafe;
  border-radius: 10px;
  background: #f8fbff;
}

.trace-progress-track {
  display: flex;
  gap: 0;
}

.trace-progress-step {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  color: #94a3b8;
}

.trace-progress-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: currentColor;
  flex-shrink: 0;
}

.trace-progress-label {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.trace-progress-line {
  height: 2px;
  background: currentColor;
  opacity: 0.35;
  flex: 1;
  margin: 0 10px;
}

.trace-progress-step.is-complete {
  color: #16a34a;
}

.trace-progress-step.is-active {
  color: #2563eb;
}

.trace-progress-step.is-active .trace-progress-dot {
  animation: trace-progress-pulse 1s ease-in-out infinite;
}

.trace-progress-step.is-error {
  color: #dc2626;
}

.trace-progress-error {
  margin: 10px 0 0;
  color: #b91c1c;
  font-size: 12px;
}

@keyframes trace-progress-pulse {
  0% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.35);
    opacity: 0.6;
  }
  100% {
    transform: scale(1);
    opacity: 1;
  }
}

@media (max-width: 840px) {
  .trace-progress-track {
    flex-direction: column;
    gap: 8px;
  }

  .trace-progress-line {
    display: none;
  }
}
</style>
