<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';

import AiChatMessage from './AiChatMessage.vue';

interface AiMessage {
  role: 'user' | 'ai' | 'clarification' | 'error' | 'loading';
  content?: string;
  [key: string]: unknown;
}

interface Props {
  messages?: AiMessage[];
  isLoading?: boolean;
  isRateLimited?: boolean;
  canSubmit?: boolean;
  loadingStepText?: string;
}

const props = withDefaults(defineProps<Props>(), {
  messages: () => [],
  isLoading: false,
  isRateLimited: false,
  canSubmit: true,
  loadingStepText: '',
});

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'submit', text: string): void;
  (e: 'reset'): void;
}>();

const inputText = ref('');
const messagesContainer = ref<HTMLElement | null>(null);


function scrollToBottom() {
  nextTick(() => {
    const el = messagesContainer.value;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  });
}

watch(
  () => props.messages.length,
  () => scrollToBottom(),
);

watch(
  () => props.isLoading,
  () => scrollToBottom(),
);

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    handleSubmit();
  }
}

function handleSubmit() {
  const text = inputText.value.trim();
  if (!text || !props.canSubmit) return;
  inputText.value = '';
  emit('submit', text);
}

function handleSuggestion(text: string) {
  emit('submit', text);
}

function handleEsc(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    emit('close');
  }
}

/**
 * Returns true if a divider should be shown before messages[idx].
 * Condition: idx > 0, messages[idx-1].role === 'ai', messages[idx].role === 'user'
 */
function showDividerBefore(idx: number) {
  if (idx === 0) return false;
  const prev = props.messages[idx - 1];
  const curr = props.messages[idx];
  return (prev?.role === 'ai' || prev?.role === 'clarification') && curr?.role === 'user';
}
</script>

<template>
  <Teleport to="body">
    <!-- Mobile overlay -->
    <Transition name="overlay-fade">
      <div
        v-if="true"
        class="ai-mobile-overlay"
        @click="emit('close')"
      />
    </Transition>

    <div
      class="ai-chat-panel"
      role="dialog"
      aria-label="AI 助手"
      @keydown="handleEsc"
    >
      <!-- Header -->
      <div class="ai-chat-header">
        <div class="ai-chat-header-left">
          <h2 class="ai-chat-title">AI 助手</h2>
        </div>
        <div class="ai-chat-header-right">
          <button
            type="button"
            class="ai-chat-btn-reset"
            @click="emit('reset')"
          >
            清除紀錄
          </button>
          <button
            type="button"
            class="ai-chat-btn-close"
            aria-label="關閉"
            @click="emit('close')"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <line x1="3" y1="3" x2="13" y2="13" />
              <line x1="13" y1="3" x2="3" y2="13" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Messages -->
      <div ref="messagesContainer" class="ai-chat-messages">
        <div
          v-if="messages.length === 0 && !isLoading"
          class="ai-chat-empty"
        >
          請輸入您的問題，例如：WB 線最近 7 天不良率如何？
        </div>

        <template v-for="(msg, idx) in messages" :key="idx">
          <!-- Conversation divider between ai reply and next user message -->
          <div v-if="showDividerBefore(idx)" class="ai-conversation-divider">
            <span class="ai-divider-line" />
            <span class="ai-divider-text">新的查詢</span>
            <span class="ai-divider-line" />
          </div>

          <AiChatMessage
            :message="msg"
            @suggest="handleSuggestion"
          />
        </template>

        <!-- Loading indicator -->
        <AiChatMessage
          v-if="isLoading"
          :message="{ role: 'loading', content: '' }"
          :step-text="loadingStepText"
        />
      </div>

      <!-- Input bar -->
      <div class="ai-chat-input-bar">
        <div
          v-if="isRateLimited"
          class="ai-chat-input-notice"
        >
          請稍候...
        </div>
        <div v-else class="ai-chat-input-row">
          <textarea
            v-model="inputText"
            class="ai-chat-textarea"
            rows="2"
            placeholder="輸入問題..."
            :disabled="!canSubmit"
            @keydown="handleKeydown"
          />
          <button
            type="button"
            class="ai-chat-btn-send"
            :disabled="!canSubmit || !inputText.trim()"
            @click="handleSubmit"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ai-mobile-overlay {
  display: none;
}

@media (max-width: 768px) {
  .ai-mobile-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 49;
  }
}

.ai-chat-panel {
  position: fixed;
  right: 0;
  top: var(--shell-header-height, 56px);
  width: 380px;
  height: calc(100vh - var(--shell-header-height, 56px));
  z-index: 50;
  background: theme('colors.surface.card');
  border-left: 1px solid theme('colors.stroke.soft');
  box-shadow: theme('boxShadow.md');
  display: flex;
  flex-direction: column;
  animation: ai-panel-slide-in var(--motion-normal, 200ms) var(--motion-ease, ease) both;
}

@keyframes ai-panel-slide-in {
  from {
    transform: translateX(100%);
  }
  to {
    transform: translateX(0);
  }
}

@media (max-width: 768px) {
  .ai-chat-panel {
    width: 100vw;
  }
}

.ai-chat-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: theme('spacing.token.p12') theme('spacing.token.p16');
  border-bottom: 1px solid theme('colors.stroke.soft');
}

.ai-chat-header-left {
  display: flex;
  align-items: center;
  gap: theme('spacing.token.p8');
}

.ai-chat-title {
  font-size: 15px;
  font-weight: 700;
  color: theme('colors.text.primary');
  margin: 0;
}

.ai-chat-header-right {
  display: flex;
  align-items: center;
  gap: theme('spacing.token.p8');
}

.ai-chat-btn-reset {
  font-size: 12px;
  color: theme('colors.brand.600');
  background: none;
  border: 1px solid theme('colors.brand.100');
  border-radius: theme('borderRadius.card');
  padding: theme('spacing.token.p3') theme('spacing.token.p10');
  cursor: pointer;
  transition: background var(--motion-fast) var(--motion-ease);
}

.ai-chat-btn-reset:hover {
  background: theme('colors.brand.50');
}

.ai-chat-btn-close {
  background: none;
  border: none;
  color: theme('colors.text.muted');
  cursor: pointer;
  padding: theme('spacing.token.p4');
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: theme('borderRadius.card');
  transition: background var(--motion-fast) var(--motion-ease);
}

.ai-chat-btn-close:hover {
  background: theme('colors.surface.hover');
}

.ai-chat-messages {
  flex: 1 1 0;
  overflow-y: auto;
  padding: theme('spacing.token.p16');
  scrollbar-width: thin;
  scrollbar-color: theme('colors.stroke.soft') transparent;
}

.ai-chat-messages::-webkit-scrollbar {
  width: 4px;
}

.ai-chat-messages::-webkit-scrollbar-thumb {
  background: theme('colors.stroke.soft');
  border-radius: 2px;
}

.ai-chat-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  height: 100%;
  color: theme('colors.text.muted');
  font-size: 13px;
  padding: theme('spacing.token.p24');
  line-height: 1.6;
}

.ai-chat-input-bar {
  flex-shrink: 0;
  border-top: 1px solid theme('colors.stroke.soft');
  padding: theme('spacing.token.p12');
}

.ai-chat-input-notice {
  text-align: center;
  color: theme('colors.text.muted');
  font-size: 13px;
  padding: theme('spacing.token.p8');
}

.ai-chat-input-row {
  display: flex;
  gap: theme('spacing.token.p8');
  align-items: flex-end;
}

.ai-chat-textarea {
  flex: 1;
  resize: none;
  border: 1px solid theme('colors.stroke.input');
  border-radius: theme('borderRadius.card');
  padding: theme('spacing.token.p8');
  font-size: 13px;
  font-family: inherit;
  line-height: 1.5;
  outline: none;
  transition: border-color var(--motion-fast) var(--motion-ease);
}

.ai-chat-textarea:focus {
  border-color: theme('colors.brand.500');
}

.ai-chat-textarea:disabled {
  background: theme('colors.surface.muted');
  cursor: not-allowed;
}

.ai-chat-btn-send {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: theme('colors.brand.600');
  color: theme('colors.token.hffffff');
  border: none;
  border-radius: theme('borderRadius.card');
  cursor: pointer;
  transition: background var(--motion-fast) var(--motion-ease);
}

.ai-chat-btn-send:hover:not(:disabled) {
  background: theme('colors.brand.700');
}

.ai-chat-btn-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity var(--motion-normal) var(--motion-ease);
}

.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}
</style>
