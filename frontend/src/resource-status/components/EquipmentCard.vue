<script setup>
import { computed } from 'vue';

import { getStatusDisplay, normalizeStatus } from '../../resource-shared/constants.js';

const props = defineProps({
  equipment: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(['show-lot', 'show-job']);

const statusKey = computed(() => normalizeStatus(props.equipment.EQUIPMENTASSETSSTATUS));

const statusClass = computed(() => {
  const category = String(props.equipment.STATUS_CATEGORY || '').toLowerCase();
  if (category) {
    return category;
  }
  return statusKey.value.toLowerCase();
});

const statusLabel = computed(() => getStatusDisplay(props.equipment.EQUIPMENTASSETSSTATUS));
const lotCount = computed(() => Number(props.equipment.LOT_COUNT || 0));
const hasJob = computed(() => Boolean(props.equipment.JOBORDER));

function emitLot(event) {
  event.stopPropagation();
  emit('show-lot', {
    x: event.clientX,
    y: event.clientY,
    equipment: props.equipment,
  });
}

function emitJob(event) {
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
    </div>

    <div class="info-triggers">
      <button v-if="lotCount > 0" type="button" class="info-trigger" @click="emitLot">LOT {{ lotCount }}</button>
      <button v-if="hasJob" type="button" class="info-trigger" @click="emitJob">
        JOB {{ equipment.JOBORDER }}
      </button>
    </div>
  </article>
</template>
