<script setup>
defineProps({
  reason: {
    type: String,
    default: '',
  },
  durationRange: {
    type: String,
    default: '',
  },
});

const emit = defineEmits(['clear-reason', 'clear-duration']);
</script>

<template>
  <section v-if="reason || durationRange" class="reason-filter-indicator">
    <span v-if="reason" class="filter-chip reason">Reason 篩選：{{ reason }}</span>
    <button v-if="reason" type="button" class="ui-btn ui-btn--ghost clear-reason-btn" @click="emit('clear-reason')">
      ✕ 清除
    </button>
    <span v-if="durationRange" class="filter-chip duration">時長篩選：{{ durationRange }}</span>
    <button
      v-if="durationRange"
      type="button"
      class="ui-btn ui-btn--ghost clear-reason-btn"
      @click="emit('clear-duration')"
    >
      ✕ 清除
    </button>
  </section>
</template>
