<script setup lang="ts">
import { computed } from 'vue';

import { getStatusDisplay, normalizeStatus } from '../../resource-shared/constants';

interface LotItem {
  RUNCARDLOTID?: string;
  LOTTRACKINQTY_PCS?: number | null;
  LOTTRACKINTIME?: string | null;
  BOP?: string | null;
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

const props = defineProps<{
  equipment: EquipmentItem;
}>();

const emit = defineEmits<{
  'show-lot': [payload: TooltipPayload];
  'show-job': [payload: TooltipPayload];
}>();

const statusKey = computed(() => normalizeStatus(props.equipment.EQUIPMENTASSETSSTATUS));

const statusClass = computed<string>(() => {
  const category = String(props.equipment.STATUS_CATEGORY || '').toLowerCase();
  if (category) {
    return category;
  }
  return statusKey.value.toLowerCase();
});

const statusLabel = computed<string>(() => getStatusDisplay(props.equipment.EQUIPMENTASSETSSTATUS));
const lotCount = computed<number>(() => Number(props.equipment.LOT_COUNT || 0));
const hasJob = computed<boolean>(() => Boolean(props.equipment.JOBORDER));

const bopDisplay = computed<string>(() => {
  const lots = props.equipment.LOT_DETAILS ?? [];
  const unique = [...new Set(lots.map(l => l.BOP).filter((b): b is string => Boolean(b)))];
  return unique.join(', ');
});

function emitLot(event: MouseEvent): void {
  event.stopPropagation();
  emit('show-lot', {
    x: event.clientX,
    y: event.clientY,
    equipment: props.equipment,
  });
}

function emitJob(event: MouseEvent): void {
  event.stopPropagation();
  emit('show-job', {
    x: event.clientX,
    y: event.clientY,
    equipment: props.equipment,
  });
}
</script>

<template>
  <article class="equipment-card" :class="`status-${statusClass}`">
    <div class="eq-header">
      <div class="eq-name">{{ equipment.RESOURCENAME || equipment.RESOURCEID || '--' }}</div>
      <span class="eq-status" :class="statusClass">{{ statusLabel }}</span>
    </div>

    <div class="eq-info">
      <span class="eq-info-item">
        <span class="label">工站</span>
        <span class="value">{{ equipment.WORKCENTERNAME || '--' }}</span>
      </span>
      <span class="eq-info-item">
        <span class="label">群組</span>
        <span class="value">{{ equipment.WORKCENTER_GROUP || '--' }}</span>
      </span>
      <span class="eq-info-item">
        <span class="label">型號</span>
        <span class="value">{{ equipment.RESOURCEFAMILYNAME || '--' }}</span>
      </span>
      <span class="eq-info-item">
        <span class="label">位置</span>
        <span class="value">{{ equipment.LOCATIONNAME || '--' }}</span>
      </span>
      <span v-if="equipment.PACKAGEGROUPNAME" class="eq-info-item">
        <span class="label">Package</span>
        <span class="value">{{ equipment.PACKAGEGROUPNAME }}</span>
      </span>
      <span v-if="bopDisplay" class="eq-info-item">
        <span class="label">BOP</span>
        <span class="value">{{ bopDisplay }}</span>
      </span>
    </div>

    <div class="info-triggers">
      <button v-if="lotCount > 0" type="button" class="info-trigger" @click="emitLot">LOT {{ lotCount }}</button>
      <button v-if="hasJob" type="button" class="info-trigger" @click="emitJob">
        JOB {{ equipment.JOBORDER }}
      </button>
    </div>
  </article>
</template>
