<script setup>
import { computed } from 'vue';

const props = defineProps({
  tone: {
    type: String,
    default: 'neutral',
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
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.tone-neutral {
  background: #e2e8f0;
  color: #334155;
}

.tone-success {
  background: #dcfce7;
  color: #166534;
}

.tone-warning {
  background: #fef3c7;
  color: #92400e;
}

.tone-danger {
  background: #fee2e2;
  color: #b91c1c;
}
</style>
