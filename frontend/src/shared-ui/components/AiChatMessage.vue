<script setup>
import StatusBadge from './StatusBadge.vue';
import AiChartRenderer from './AiChartRenderer.vue';

defineProps({
  message: {
    type: Object,
    required: true,
  },
  stepText: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['suggest']);
</script>

<template>
  <div class="ai-chat-msg" :class="`ai-chat-msg--${message.role}`">
    <!-- User message -->
    <div v-if="message.role === 'user'" class="ai-msg-user">
      {{ message.content }}
    </div>

    <!-- AI message -->
    <div v-else-if="message.role === 'ai'" class="ai-msg-ai">
      <p v-if="message.content" class="text-sm text-text-primary whitespace-pre-wrap">
        {{ message.content }}
      </p>

      <div v-if="message.queryUsed" class="ai-msg-query-used">
        <span class="text-xs text-text-secondary">使用了：</span>
        <StatusBadge tone="neutral" :text="message.queryUsed" />
      </div>

      <AiChartRenderer
        v-if="message.chartData"
        :chart-data="message.chartData"
        :query-used="message.queryUsed"
      />

      <div
        v-if="message.suggestions && message.suggestions.length > 0"
        class="ai-msg-suggestions"
      >
        <button
          v-for="(suggestion, idx) in message.suggestions"
          :key="idx"
          type="button"
          class="ai-suggestion-chip"
          @click="emit('suggest', suggestion)"
        >
          {{ suggestion }}
        </button>
      </div>
    </div>

    <!-- Error message -->
    <div v-else-if="message.role === 'error'" class="ai-msg-error">
      {{ message.content }}
    </div>

    <!-- Loading indicator -->
    <div v-else-if="message.role === 'loading'" class="ai-msg-ai">
      <div class="ai-typing-indicator">
        <span class="ai-typing-dot" />
        <span class="ai-typing-dot" />
        <span class="ai-typing-dot" />
        <span v-if="stepText" class="ai-step-text">{{ stepText }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ai-chat-msg {
  display: flex;
  margin-bottom: theme('spacing.token.p8');
}

.ai-chat-msg--user {
  justify-content: flex-end;
}

.ai-chat-msg--ai,
.ai-chat-msg--loading,
.ai-chat-msg--error {
  justify-content: flex-start;
}

.ai-msg-user {
  background: theme('colors.brand.50');
  border-radius: 12px;
  padding: theme('spacing.token.p8') theme('spacing.token.p12');
  font-size: 14px;
  max-width: 85%;
  margin-left: auto;
  word-break: break-word;
}

.ai-msg-ai {
  display: flex;
  flex-direction: column;
  gap: theme('spacing.token.p8');
  max-width: 95%;
}

.ai-msg-error {
  background: theme('colors.red.50');
  color: theme('colors.red.700');
  border-radius: 12px;
  padding: theme('spacing.token.p8') theme('spacing.token.p12');
  font-size: 14px;
  border: 1px solid theme('colors.red.200');
}

.ai-msg-query-used {
  display: flex;
  align-items: center;
  gap: theme('spacing.token.p4');
  flex-wrap: wrap;
}

.ai-msg-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: theme('spacing.token.p8');
}

.ai-suggestion-chip {
  display: inline-flex;
  align-items: center;
  background: theme('colors.brand.50');
  color: theme('colors.brand.700');
  border: 1px solid theme('colors.brand.100');
  border-radius: 9999px;
  padding: theme('spacing.token.p4') theme('spacing.token.p12');
  font-size: 12px;
  cursor: pointer;
  transition: background var(--motion-fast) var(--motion-ease);
}

.ai-suggestion-chip:hover:not(:disabled) {
  background: theme('colors.brand.100');
}
</style>
