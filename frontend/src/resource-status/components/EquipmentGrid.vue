<script setup>
import EquipmentCard from './EquipmentCard.vue';

const props = defineProps({
  equipment: {
    type: Array,
    default: () => [],
  },
  activeFilterText: {
    type: String,
    default: '',
  },
});

defineEmits(['clear-filter', 'show-lot', 'show-job']);
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="section-header">
        <h2 class="section-title">設備清單</h2>
        <span class="equipment-count">共 {{ equipment.length }} 台</span>
      </div>

      <div class="filter-indicator" :class="{ active: Boolean(activeFilterText) }">
        <span class="filter-text">{{ activeFilterText }}</span>
        <button type="button" class="btn-sm" @click="$emit('clear-filter')">清除篩選</button>
      </div>

      <div v-if="equipment.length" class="equipment-grid">
        <EquipmentCard
          v-for="eq in equipment"
          :key="eq.RESOURCEID || eq.RESOURCENAME"
          :equipment="eq"
          @show-lot="$emit('show-lot', $event)"
          @show-job="$emit('show-job', $event)"
        />
      </div>
      <div v-else class="empty-state">無符合條件的設備</div>
    </div>
  </section>
</template>
