<script setup lang="ts">
interface Props {
  reason?: string;
  durationRange?: string;
  dayFilter?: string;
}

withDefaults(defineProps<Props>(), {
  reason: '',
  durationRange: '',
  dayFilter: '',
});

const emit = defineEmits<{
  'clear-reason': [];
  'clear-duration': [];
  'clear-day': [];
}>();
</script>

<template>
  <section v-if="reason || durationRange || dayFilter" class="reason-filter-indicator">
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
    <span v-if="dayFilter" class="filter-chip day">日期篩選：{{ dayFilter.split(':')[0] }} · {{ dayFilter.split(':')[1] === 'release' ? 'Release' : '新增' }}</span>
    <button
      v-if="dayFilter"
      type="button"
      class="ui-btn ui-btn--ghost clear-reason-btn"
      @click="emit('clear-day')"
    >
      ✕ 清除
    </button>
  </section>
</template>
