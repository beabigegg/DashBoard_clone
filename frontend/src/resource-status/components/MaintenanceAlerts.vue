<script setup lang="ts">
import { computed, ref } from 'vue';

import { STATUS_DISPLAY_MAP } from '../../resource-shared/constants';

interface EquipmentItem {
  RESOURCEID: string;
  RESOURCENAME: string;
  WORKCENTER_GROUP: string;
  JOBORDER: string;
  JOBSTATUS: string;
  JOBMODEL: string;
  CREATEDATE: string;
  TECHNICIANUSERNAME: string;
  SYMPTOMCODE: string;
  CAUSECODE: string;
  REPAIRCODE: string;
}

const props = defineProps<{
  equipment: EquipmentItem[];
  lastUpdate: string;
}>();

const emit = defineEmits<{
  'show-job': [{ x: number; y: number; equipment: EquipmentItem }];
}>();

function handleJobClick(event: MouseEvent, eq: EquipmentItem): void {
  if (!eq.JOBORDER?.trim()) return;
  emit('show-job', { x: event.clientX, y: event.clientY, equipment: eq });
}

function parseLocalDate(s: string): Date | null {
  if (!s || s === '--') return null;
  const clean = s.replace('T', ' ').replace(/\.\d+$/, '');
  const [datePart, timePart = '00:00:00'] = clean.split(' ');
  const parts = datePart.split('-').map(Number);
  const timeParts = timePart.split(':').map(Number);
  const [y, mo, d] = parts;
  const [h = 0, mi = 0, se = 0] = timeParts;
  if (!y || !mo || !d) return null;
  return new Date(y, mo - 1, d, h, mi, se);
}

function formatDuration(ms: number): string {
  if (ms <= 0) return '0m';
  const totalMins = Math.floor(ms / 60000);
  const h = Math.floor(totalMins / 60);
  const m = totalMins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// rank 0-indexed: 0-2 red, 3-5 orange, 6-9 yellow
const RANK_COLORS = [
  'var(--color-token-hef4444)', 'var(--color-token-hef4444)', 'var(--color-token-hef4444)',
  'var(--color-token-hf97316)', 'var(--color-token-hf97316)', 'var(--color-token-hf97316)',
  'var(--color-token-heab308)', 'var(--color-token-heab308)', 'var(--color-token-heab308)', 'var(--color-token-heab308)',
];

interface AlertItem {
  eq: EquipmentItem;
  durationMs: number;
  durationLabel: string;
}

const referenceTime = computed(() => parseLocalDate(props.lastUpdate) ?? new Date());

const top10 = computed<AlertItem[]>(() => {
  const withJob = props.equipment.filter((eq) => eq.JOBORDER?.trim());

  const items: AlertItem[] = withJob.map((eq) => {
    const created = parseLocalDate(eq.CREATEDATE);
    const durationMs = created ? Math.max(0, referenceTime.value.getTime() - created.getTime()) : 0;
    return { eq, durationMs, durationLabel: formatDuration(durationMs) };
  });

  items.sort((a, b) => b.durationMs - a.durationMs);
  return items.slice(0, 10);
});

const maxDuration = computed(() => Math.max(1, ...top10.value.map((a) => a.durationMs)));

function barWidth(ms: number): string {
  return `${Math.max(4, Math.round((ms / maxDuration.value) * 100))}%`;
}

const collapsed = ref(true);

function jobStatusLabel(status: string): string {
  return STATUS_DISPLAY_MAP[status?.toUpperCase()] || status || '--';
}
</script>

<template>
  <section class="alerts-section">
    <button class="alerts-toggle" @click="collapsed = !collapsed">
      <span class="section-title alerts-title-row">
        維修告警 Top 10
        <span class="alerts-hint">依持續時間</span>
        <span class="alerts-count-badge" v-if="top10.length > 0">{{ top10.length }}</span>
      </span>
      <span class="alerts-chevron" :class="{ 'is-open': !collapsed }">▼</span>
    </button>
    <template v-if="!collapsed">
    <div v-if="top10.length === 0" class="empty-hint">目前無進行中維修工單</div>
    <div v-else class="alerts-list">
      <div
        v-for="(item, idx) in top10"
        :key="item.eq.RESOURCEID + item.eq.JOBORDER"
        class="alert-card"
        :style="{ borderLeftColor: RANK_COLORS[idx] }"
      >
        <div class="alert-header">
          <span class="rank-badge" :style="{ background: RANK_COLORS[idx] }">{{ idx + 1 }}</span>
          <span class="alert-resource">{{ item.eq.RESOURCENAME || item.eq.RESOURCEID }}</span>
          <span class="alert-group">{{ item.eq.WORKCENTER_GROUP }}</span>
        </div>

        <div class="alert-duration-row">
          <div class="duration-bar-bg">
            <div
              class="duration-bar-fill"
              :style="{ width: barWidth(item.durationMs), background: RANK_COLORS[idx] }"
            ></div>
          </div>
          <span class="duration-label">{{ item.durationLabel }}</span>
        </div>

        <div class="alert-meta">
          <span class="job-chip job-chip--clickable" @click="handleJobClick($event, item.eq)">{{ item.eq.JOBORDER }}</span>
          <span v-if="item.eq.JOBSTATUS" class="job-status-chip">{{ jobStatusLabel(item.eq.JOBSTATUS) }}</span>
          <span v-if="item.eq.JOBMODEL" class="job-model-chip">{{ item.eq.JOBMODEL }}</span>
        </div>

        <div class="alert-detail">
          <span v-if="item.eq.TECHNICIANUSERNAME" class="detail-item">技師: {{ item.eq.TECHNICIANUSERNAME }}</span>
          <span v-if="item.eq.SYMPTOMCODE" class="detail-item">症: {{ item.eq.SYMPTOMCODE }}</span>
          <span v-if="item.eq.CAUSECODE" class="detail-item">因: {{ item.eq.CAUSECODE }}</span>
          <span v-if="item.eq.REPAIRCODE" class="detail-item">修: {{ item.eq.REPAIRCODE }}</span>
        </div>
      </div>
    </div>
    </template>
  </section>
</template>
