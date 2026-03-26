<script setup>
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

const props = defineProps({
  workcenterGroups: {
    type: Array,
    default: () => [],
  },
  selectedGroups: {
    type: Array,
    default: () => [],
  },
  flags: {
    type: Object,
    default: () => ({
      isProduction: false,
      isKey: false,
      isMonitor: false,
    }),
  },
  familyOptions: {
    type: Array,
    default: () => [],
  },
  machineOptions: {
    type: Array,
    default: () => [],
  },
  selectedFamilies: {
    type: Array,
    default: () => [],
  },
  selectedMachines: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['change-groups', 'change-flags', 'change-families', 'change-machines']);

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
        <label>工站群組</label>
        <MultiSelect
          :model-value="selectedGroups"
          :options="workcenterGroups"
          :disabled="loading"
          placeholder="全部群組"
          @update:model-value="$emit('change-groups', $event)"
        />
      </div>

      <div class="filter-block">
        <label>型號</label>
        <MultiSelect
          :model-value="selectedFamilies"
          :options="familyOptions"
          :disabled="loading"
          placeholder="全部型號"
          @update:model-value="$emit('change-families', $event)"
        />
      </div>

      <div class="filter-block">
        <label>機台</label>
        <MultiSelect
          :model-value="selectedMachines"
          :options="machineOptions"
          :disabled="loading"
          placeholder="全部機台"
          searchable
          @update:model-value="$emit('change-machines', $event)"
        />
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
