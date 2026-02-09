<script setup>
const props = defineProps({
  workcenterGroups: {
    type: Array,
    default: () => [],
  },
  selectedGroup: {
    type: String,
    default: '',
  },
  flags: {
    type: Object,
    default: () => ({
      isProduction: false,
      isKey: false,
      isMonitor: false,
    }),
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['change-group', 'change-flags']);

function updateFlag(key, checked) {
  emit('change-flags', {
    ...props.flags,
    [key]: checked,
  });
}
</script>

<template>
  <section class="section-card">
    <div class="filters-panel">
      <div class="filter-block">
        <label for="status-group-filter">工站群組</label>
        <select
          id="status-group-filter"
          class="filter-select"
          :value="selectedGroup"
          :disabled="loading"
          @change="$emit('change-group', $event.target.value)"
        >
          <option value="">全部群組</option>
          <option v-for="group in workcenterGroups" :key="group" :value="group">
            {{ group }}
          </option>
        </select>
      </div>

      <label class="filter-chip" :class="{ active: flags.isProduction }">
        <input
          type="checkbox"
          :checked="flags.isProduction"
          :disabled="loading"
          @change="updateFlag('isProduction', $event.target.checked)"
        />
        生產設備
      </label>

      <label class="filter-chip" :class="{ active: flags.isKey }">
        <input
          type="checkbox"
          :checked="flags.isKey"
          :disabled="loading"
          @change="updateFlag('isKey', $event.target.checked)"
        />
        重點設備
      </label>

      <label class="filter-chip" :class="{ active: flags.isMonitor }">
        <input
          type="checkbox"
          :checked="flags.isMonitor"
          :disabled="loading"
          @change="updateFlag('isMonitor', $event.target.checked)"
        />
        監控設備
      </label>
    </div>
  </section>
</template>
