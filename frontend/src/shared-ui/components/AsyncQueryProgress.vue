<script setup lang="ts">
import LoadingSpinner from './LoadingSpinner.vue';

interface Props {
  active: boolean;
  progress: string;
  pct: number;
  elapsedSeconds: number;
  canCancel?: boolean;
  status?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
  canCancel: true,
  status: null,
});

const emit = defineEmits<{
  (e: 'cancel'): void;
}>();
</script>

<template>
  <div v-if="props.active" class="async-job-progress" :class="{ 'async-job-progress--failed': props.status === 'failed' }" role="status" aria-live="polite">
    <div class="async-job-progress__bar-track" aria-hidden="true">
      <div
        class="async-job-progress__bar-fill"
        :class="{ 'async-job-progress__bar-fill--error': props.status === 'failed' }"
        :style="{ width: props.pct + '%' }"
      />
    </div>
    <div class="async-job-progress__body">
      <LoadingSpinner v-if="props.status !== 'failed'" size="sm" />
      <span v-if="props.status === 'failed'" class="async-job-progress__error-icon" aria-hidden="true">✕</span>
      <span class="async-job-progress__label" :class="{ 'async-job-progress__label--error': props.status === 'failed' }">
        {{ props.status === 'failed' ? (props.progress || '查詢失敗') : (props.progress || '背景查詢中...') }}
      </span>
      <span class="async-job-progress__pct">{{ props.pct }}%</span>
      <span v-if="props.elapsedSeconds > 0" class="async-job-progress__elapsed">
        已等待 {{ props.elapsedSeconds }} 秒
      </span>
      <button
        v-if="props.canCancel !== false"
        type="button"
        class="async-job-progress__cancel ui-btn ui-btn--ghost ui-btn--sm"
        @click="emit('cancel')"
      >
        取消查詢
      </button>
    </div>
  </div>
</template>

<style scoped>
.async-job-progress {
  display: flex;
  flex-direction: column;
  gap: theme('spacing.token.p6');
  padding: theme('spacing.token.p10') theme('spacing.token.p12');
  background-color: theme('colors.token.heff6ff');
  border: 1px solid theme('colors.token.hbfdbfe');
  border-radius: theme('borderRadius.button');
  margin-bottom: theme('spacing.token.p12');
}

.async-job-progress__bar-track {
  height: theme('spacing.token.p6');
  background-color: theme('colors.token.hdbeafe');
  border-radius: theme('borderRadius.pill');
  overflow: hidden;
}

.async-job-progress__bar-fill {
  height: 100%;
  background-color: theme('colors.token.h3b82f6');
  border-radius: theme('borderRadius.pill');
  transition: width 0.4s ease;
}

@media (prefers-reduced-motion: reduce) {
  .async-job-progress__bar-fill {
    transition: none;
  }
}

.async-job-progress__body {
  display: flex;
  align-items: center;
  gap: theme('spacing.token.p8');
  flex-wrap: wrap;
  font-size: theme('fontSize.sm');
  color: theme('colors.token.h1e40af');
}

.async-job-progress__label {
  flex: 1 1 auto;
}

.async-job-progress__pct {
  font-weight: 600;
}

.async-job-progress__elapsed {
  color: theme('colors.token.h3b82f6');
}

.async-job-progress__cancel {
  margin-left: auto;
  flex-shrink: 0;
}

/* ── Failed state ─────────────────────────────────────────────────────────── */
.async-job-progress--failed {
  background-color: theme('colors.token.hfef2f2');
  border-color: theme('colors.token.hfecaca');
}

.async-job-progress__bar-fill--error {
  background-color: theme('colors.token.hdc2626');
}

.async-job-progress__error-icon {
  font-weight: 700;
  color: theme('colors.token.hdc2626');
}

.async-job-progress__label--error {
  color: theme('colors.token.hb91c1c');
}
</style>
