<script setup>
defineProps({
  type: {
    type: String,
    default: 'no-data',
    validator: (v) => ['no-data', 'filter-empty', 'error', 'loading'].includes(v),
  },
});

const messages = {
  'no-data': '目前沒有資料',
  'filter-empty': '找不到符合條件的資料',
  'error': '資料載入失敗，請稍後再試',
  'loading': '資料載入中...',
};
</script>

<template>
  <div class="empty-state">
    <slot name="icon" />
    <p class="empty-state__message">{{ messages[type] }}</p>
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

.empty-state__message {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--portal-text-secondary, #64748b);
}
</style>
