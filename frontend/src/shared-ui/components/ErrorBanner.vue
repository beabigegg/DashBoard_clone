<script setup lang="ts">
interface Props {
  message?: string;
  dismissible?: boolean;
}

withDefaults(defineProps<Props>(), {
  message: '',
  dismissible: true,
});

const emit = defineEmits<{
  (e: 'dismiss'): void;
}>();
</script>

<template>
  <div v-if="message" class="error-banner-wrap" role="alert">
    <span class="error-banner-message">{{ message }}</span>
    <div class="error-banner-actions">
      <slot name="action" />
      <button
        v-if="dismissible"
        type="button"
        class="error-banner-dismiss"
        aria-label="關閉錯誤訊息"
        @click="emit('dismiss')"
      >
        ✕
      </button>
    </div>
  </div>
</template>

<style scoped>
.error-banner-wrap {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: theme('spacing.token.p10') theme('spacing.token.p14');
  border: 1px solid theme('colors.token.hfecaca');
  border-radius: 8px;
  background: theme('colors.token.hfef2f2');
  color: theme('colors.token.h991b1b');
  font-size: 13px;
  margin-bottom: theme('spacing.token.p14');
}

.error-banner-message {
  flex: 1;
  min-width: 0;
}

.error-banner-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.error-banner-dismiss {
  border: none;
  background: transparent;
  color: theme('colors.token.h991b1b');
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 4px;
  opacity: 0.7;
}

.error-banner-dismiss:hover {
  opacity: 1;
  background: theme('colors.token.hfecaca');
}
</style>
