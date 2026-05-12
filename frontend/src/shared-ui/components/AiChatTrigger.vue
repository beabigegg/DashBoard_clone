<script setup lang="ts">
defineEmits<{
  (e: 'click'): void;
}>();
</script>

<template>
  <button
    type="button"
    class="ai-chat-trigger"
    aria-label="開啟 AI 助手"
    @click="$emit('click')"
  >
    <svg
      class="ai-chat-trigger-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <circle cx="9" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="10" r="1" fill="currentColor" stroke="none" />
    </svg>
  </button>
</template>

<style scoped>
.ai-chat-trigger {
  position: fixed;
  right: 24px;
  bottom: 24px;
  width: 48px;
  height: 48px;
  border-radius: 9999px;
  background: theme('colors.brand.600');
  color: theme('colors.token.hffffff');
  border: none;
  box-shadow: theme('boxShadow.md');
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  transition: background var(--motion-fast) var(--motion-ease);
}

.ai-chat-trigger:hover {
  background: theme('colors.brand.700');
}

.ai-chat-trigger-icon {
  width: 24px;
  height: 24px;
}

@media (max-width: 768px) {
  .ai-chat-trigger {
    width: 40px;
    height: 40px;
  }

  .ai-chat-trigger-icon {
    width: 20px;
    height: 20px;
  }
}
</style>
