<script setup lang="ts">
import EquipmentCard from './EquipmentCard.vue';

interface LotItem {
  RUNCARDLOTID?: string;
  LOTTRACKINQTY_PCS?: number | null;
  LOTTRACKINTIME?: string | null;
}

interface EquipmentItem {
  RESOURCEID: string;
  RESOURCENAME: string;
  EQUIPMENTASSETSSTATUS: string;
  WORKCENTER_GROUP: string;
  WORKCENTER_GROUP_SEQ: number;
  RESOURCEFAMILYNAME: string;
  WORKCENTERNAME: string;
  LOCATIONNAME: string;
  LOT_COUNT: number | string;
  LOT_DETAILS: LotItem[];
  JOBORDER: string;
  JOBSTATUS: string;
  JOBMODEL: string;
  JOBSTAGE: string;
  JOBID: string;
  CREATEDATE: string;
  CREATEUSERNAME: string;
  CREATEUSER: string;
  TECHNICIANUSERNAME: string;
  TECHNICIANUSER: string;
  SYMPTOMCODE: string;
  CAUSECODE: string;
  REPAIRCODE: string;
  STATUS_CATEGORY: string;
  PACKAGEGROUPNAME: string | null;
}

interface TooltipPayload {
  x: number;
  y: number;
  equipment: EquipmentItem;
}

withDefaults(defineProps<{
  equipment?: EquipmentItem[];
  activeFilterText?: string;
}>(), {
  equipment: () => [],
  activeFilterText: '',
});

defineEmits<{
  'clear-filter': [];
  'show-lot': [payload: TooltipPayload];
  'show-job': [payload: TooltipPayload];
}>();
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
          data-testid="equipment-card"
          :equipment="eq"
          @show-lot="$emit('show-lot', $event)"
          @show-job="$emit('show-job', $event)"
        />
      </div>
      <div v-else class="empty-state" data-testid="empty-state">無符合條件的設備</div>
    </div>
  </section>
</template>
