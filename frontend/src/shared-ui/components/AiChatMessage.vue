<script setup lang="ts">
import StatusBadge from './StatusBadge.vue';
import AiChartRenderer from './AiChartRenderer.vue';

interface AiMessage {
  role: 'user' | 'ai' | 'clarification' | 'error' | 'loading';
  content?: string;
  queryUsed?: string;
  chartData?: unknown;
  sqlUsed?: string;
  toolTrace?: Array<{ step: number; function: string; summary: string; error?: string }>;
  suggestions?: string[];
  subtasks?: Array<{ goal: string; answer: string; success: boolean }>;
}

interface Props {
  message: AiMessage;
  stepText?: string;
}

defineProps<Props>();

const emit = defineEmits<{
  (e: 'suggest', suggestion: string): void;
}>();
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
        :chart-data="message.chartData as Record<string, unknown> | unknown[]"
        :query-used="message.queryUsed"
      />

      <details v-if="message.sqlUsed" class="ai-sql-details">
        <summary class="ai-sql-summary">查看 SQL</summary>
        <pre class="ai-sql-pre">{{ message.sqlUsed }}</pre>
      </details>

      <!-- Leader-mode subtask results (AI_MODE=leader) -->
      <details v-if="message.subtasks && message.subtasks.length > 0" class="ai-sql-details">
        <summary class="ai-sql-summary">子任務結果 ({{ message.subtasks.length }})</summary>
        <ol class="ai-subtask-list">
          <li v-for="(subtask, idx) in message.subtasks" :key="idx" class="ai-subtask-item">
            <div class="ai-subtask-header">
              <StatusBadge
                :tone="subtask.success ? 'success' : 'danger'"
                :text="subtask.success ? '成功' : '失敗'"
              />
              <span class="ai-subtask-goal">{{ subtask.goal }}</span>
            </div>
            <p class="ai-subtask-answer">{{ subtask.answer }}</p>
          </li>
        </ol>
      </details>

      <details v-if="message.toolTrace && message.toolTrace.length > 1" class="ai-sql-details">
        <summary class="ai-sql-summary">查詢步驟 ({{ message.toolTrace.length }} 步)</summary>
        <ol class="ai-trace-list">
          <li v-for="step in message.toolTrace" :key="step.step" class="ai-trace-item">
            <span class="ai-trace-fn">{{ step.function }}</span>
            <span class="ai-trace-summary">{{ step.summary }}</span>
            <span v-if="step.error" class="ai-trace-error">{{ step.error }}</span>
          </li>
        </ol>
      </details>

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

    <!-- Clarification message (AI asking for more info) -->
    <div v-else-if="message.role === 'clarification'" class="ai-msg-clarification">
      <p class="text-sm whitespace-pre-wrap">{{ message.content }}</p>
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
.ai-chat-msg--error,
.ai-chat-msg--clarification {
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

.ai-msg-clarification {
  display: flex;
  flex-direction: column;
  gap: theme('spacing.token.p8');
  max-width: 95%;
  background: theme('colors.brand.50');
  border: 1px solid theme('colors.brand.100');
  border-radius: 12px;
  padding: theme('spacing.token.p10') theme('spacing.token.p12');
  color: theme('colors.text.primary');
  font-size: 14px;
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

.ai-sql-details {
  border: 1px solid theme('colors.stroke.soft');
  border-radius: 6px;
  overflow: hidden;
}

.ai-sql-summary {
  padding: theme('spacing.token.p4') theme('spacing.token.p8');
  font-size: 12px;
  color: theme('colors.text.secondary');
  cursor: pointer;
  user-select: none;
}

.ai-sql-summary:hover {
  background: theme('colors.surface.hover');
}

.ai-sql-pre {
  margin: 0;
  padding: theme('spacing.token.p8');
  font-size: 12px;
  font-family: monospace;
  white-space: pre;
  overflow-x: auto;
  background: theme('colors.surface.muted');
  border-top: 1px solid theme('colors.stroke.soft');
}

.ai-trace-list {
  margin: 0;
  padding: theme('spacing.token.p8') theme('spacing.token.p8') theme('spacing.token.p8') theme('spacing.token.p20');
  display: flex;
  flex-direction: column;
  gap: theme('spacing.token.p4');
}

.ai-trace-item {
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ai-trace-fn {
  font-family: monospace;
  color: theme('colors.brand.600');
  font-weight: 500;
}

.ai-trace-summary {
  color: theme('colors.text.secondary');
}

.ai-trace-error {
  color: theme('colors.red.600');
  font-family: monospace;
  font-size: 11px;
}

.ai-subtask-list {
  margin: 0;
  padding: theme('spacing.token.p8');
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: theme('spacing.token.p8');
}

.ai-subtask-item {
  display: flex;
  flex-direction: column;
  gap: theme('spacing.token.p4');
  padding-bottom: theme('spacing.token.p8');
  border-bottom: 1px solid theme('colors.stroke.soft');
}

.ai-subtask-item:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.ai-subtask-header {
  display: flex;
  align-items: center;
  gap: theme('spacing.token.p8');
}

.ai-subtask-goal {
  font-size: 12px;
  font-weight: 500;
  color: theme('colors.text.primary');
  word-break: break-word;
}

.ai-subtask-answer {
  margin: 0;
  font-size: 12px;
  color: theme('colors.text.secondary');
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
