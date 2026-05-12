<script setup lang="ts">
interface Props {
  type?: 'no-data' | 'filter-empty' | 'error' | 'loading';
}

withDefaults(defineProps<Props>(), {
  type: 'no-data',
});

const messages: Record<string, string> = {
  'no-data': '目前沒有資料',
  'filter-empty': '找不到符合條件的資料',
  'error': '資料載入失敗，請稍後再試',
  'loading': '資料載入中...',
};
</script>

<template>
  <div class="empty-state">
    <div v-if="$slots.illustration" class="empty-state__illustration">
      <slot name="illustration" />
    </div>
    <slot name="icon" />
    <p class="empty-state__message">{{ messages[type] }}</p>
    <div v-if="$slots.action" class="empty-state__action">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  text-align: center;
}

.empty-state__illustration {
  margin-bottom: 8px;
}

.empty-state__message {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--portal-text-secondary);
}

.empty-state__action {
  margin-top: 16px;
}
</style>
