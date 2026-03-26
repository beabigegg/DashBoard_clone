<script setup>
import { computed } from 'vue';

const props = defineProps({
  tone: {
    type: String,
    default: 'neutral',
    validator: (v) => ['neutral', 'success', 'warning', 'danger', 'info'].includes(v),
  },
  text: {
    type: String,
    default: '',
  },
});

const badgeClass = computed(() => `shared-status-badge tone-${props.tone}`);
</script>

<template>
  <span :class="badgeClass">{{ text }}</span>
</template>

<style scoped>
.shared-status-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: theme('spacing.token.p2') theme('spacing.token.p8');
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.tone-neutral {
  background: theme('colors.slate.200');
  color: theme('colors.slate.700');
}

.tone-success {
  background: theme('colors.green.100');
  color: theme('colors.green.800');
}

.tone-warning {
  background: theme('colors.amber.100');
  color: theme('colors.amber.800');
}

.tone-danger {
  background: theme('colors.red.100');
  color: theme('colors.red.700');
}

.tone-info {
  background: theme('colors.blue.100');
  color: theme('colors.blue.700');
}
</style>
