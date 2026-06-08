<script setup lang="ts">
import MultiSelect from '../../shared-ui/components/MultiSelect.vue';

interface FilterFlags {
  isProduction: boolean;
  isKey: boolean;
  isMonitor: boolean;
}

interface MachineOption {
  label: string;
  value: string;
}

const props = withDefaults(defineProps<{
  workcenterGroups?: string[];
  selectedGroups?: string[];
  flags?: FilterFlags;
  familyOptions?: string[];
  machineOptions?: (string | number | Record<string, unknown>)[];
  selectedFamilies?: string[];
  selectedMachines?: string[];
  packageGroups?: string[];
  selectedPackageGroups?: string[];
  loading?: boolean;
}>(), {
  workcenterGroups: () => [],
  selectedGroups: () => [],
  flags: () => ({ isProduction: false, isKey: false, isMonitor: false }),
  familyOptions: () => [],
  machineOptions: () => [],
  selectedFamilies: () => [],
  selectedMachines: () => [],
  packageGroups: () => [],
  selectedPackageGroups: () => [],
  loading: false,
});

const emit = defineEmits<{
  'change-groups': [groups: string[]];
  'change-flags': [flags: FilterFlags];
  'change-families': [families: string[]];
  'change-machines': [machines: string[]];
  'change-package-groups': [groups: string[]];
}>();

function updateFlag(key: keyof FilterFlags, event: Event): void {
  const checked = (event.target as HTMLInputElement).checked;
  emit('change-flags', {
    ...props.flags,
    [key]: checked,
  });
}
</script>

<template>
  <section class="section-card">
    <div class="filters-panel">
      <div class="filter-row">
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

        <div class="filter-block">
          <label>封裝群組</label>
          <MultiSelect
            :model-value="selectedPackageGroups"
            :options="packageGroups"
            :disabled="loading"
            placeholder="全部封裝群組"
            @update:model-value="$emit('change-package-groups', $event)"
          />
        </div>
      </div>

      <div class="filter-row filter-row--chips">
        <label class="filter-chip" :class="{ active: flags.isProduction }">
          <input
            type="checkbox"
            :checked="flags.isProduction"
            :disabled="loading"
            @change="updateFlag('isProduction', $event)"
          />
          生產設備
        </label>

        <label class="filter-chip" :class="{ active: flags.isKey }">
          <input
            type="checkbox"
            :checked="flags.isKey"
            :disabled="loading"
            @change="updateFlag('isKey', $event)"
          />
          重點設備
        </label>

        <label class="filter-chip" :class="{ active: flags.isMonitor }">
          <input
            type="checkbox"
            :checked="flags.isMonitor"
            :disabled="loading"
            @change="updateFlag('isMonitor', $event)"
          />
          監控設備
        </label>
      </div>
    </div>
  </section>
</template>
