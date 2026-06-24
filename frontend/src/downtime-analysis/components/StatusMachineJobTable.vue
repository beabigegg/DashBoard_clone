<script setup lang="ts">
/**
 * StatusMachineJobTable — three-tier expandable equipment table
 *
 * Tier 1: Status group rows (UDT / SDT / EGT)
 * Tier 2: Machine rows within a status group (sorted by status hours DESC)
 * Tier 3: Lazy-loaded events per machine+status (via MachineEventRows)
 *
 * Change: downtime-analysis-page-redesign (IP-6)
 */
import { ref, computed } from 'vue';
import type { EquipmentDetailRow, DowntimeKpiShape, TierThreeEntry, ChartFilter } from '../types';
import MachineEventRows from './MachineEventRows.vue';

const props = defineProps<{
  equipmentRows: EquipmentDetailRow[];
  summaryData: DowntimeKpiShape | null;
  tierThreeCache: Record<string, TierThreeEntry>;
  chartFilter: ChartFilter;
  loading: boolean;
  exporting: boolean;
}>();

const emit = defineEmits<{
  'expand-machine': [payload: { resourceId: string; statusType: string }];
  'export': [];
}>();

const STATUS_GROUPS = ['UDT', 'SDT', 'EGT'] as const;
type StatusGroup = typeof STATUS_GROUPS[number];

/** Which Tier 1 status groups are expanded */
const expandedGroups = ref<Set<string>>(new Set());

/** Which Tier 2 machine+status combos are expanded; key = `${resource_id}|${status_type}` */
const expandedMachines = ref<Set<string>>(new Set());

/** Only show status groups allowed by chartFilter.status_types (null or empty = show all) */
const visibleGroups = computed((): StatusGroup[] => {
  const allowed = props.chartFilter.status_types;
  // Treat null OR empty array as "no filter" (show all) — B-1 fix
  if (!allowed || allowed.length === 0) return [...STATUS_GROUPS];
  return STATUS_GROUPS.filter((s) => allowed.includes(s));
});

/** Machine rows belonging to a status group: non-zero hours, sorted DESC */
function allMachinesForStatus(status: string): EquipmentDetailRow[] {
  const hoursKey = `${status.toLowerCase()}_hours` as keyof EquipmentDetailRow;
  return props.equipmentRows
    .filter((r) => ((r[hoursKey] as number) ?? 0) > 0)
    .sort((a, b) => ((b[hoursKey] as number) ?? 0) - ((a[hoursKey] as number) ?? 0));
}

/** Top 50 machines for this status (sorted by hours DESC) */
function machinesForStatus(status: string): EquipmentDetailRow[] {
  return allMachinesForStatus(status).slice(0, 50);
}

/** Total hours for the status group from KPI summary */
function groupHours(status: string): number {
  if (!props.summaryData) return 0;
  const key = `${status.toLowerCase()}_hours` as keyof DowntimeKpiShape;
  return (props.summaryData[key] as number) ?? 0;
}

/** Total count of machines with non-zero hours (before top-50 cap) */
function groupMachineCount(status: string): number {
  return allMachinesForStatus(status).length;
}

function groupEventCount(status: string): number {
  return allMachinesForStatus(status).reduce(
    (sum, m) => sum + machineStatusEventCount(m, status),
    0
  );
}

/** Hours a specific machine has for a specific status */
function machineStatusHours(machine: EquipmentDetailRow, status: string): number {
  const key = `${status.toLowerCase()}_hours` as keyof EquipmentDetailRow;
  return (machine[key] as number) ?? 0;
}

/** Event count for a specific status on this machine */
function machineStatusEventCount(machine: EquipmentDetailRow, status: string): number {
  const key = `${status.toLowerCase()}_event_count` as keyof EquipmentDetailRow;
  return (machine[key] as number) ?? 0;
}

function toggleGroup(status: string): void {
  if (expandedGroups.value.has(status)) {
    expandedGroups.value.delete(status);
  } else {
    expandedGroups.value.add(status);
  }
  // Force Vue reactivity for Set mutation
  expandedGroups.value = new Set(expandedGroups.value);
}

function toggleMachine(resourceId: string, statusType: string): void {
  const key = `${resourceId}|${statusType}`;
  if (expandedMachines.value.has(key)) {
    expandedMachines.value.delete(key);
  } else {
    expandedMachines.value.add(key);
  }
  expandedMachines.value = new Set(expandedMachines.value);
}

function isMachineExpanded(resourceId: string, statusType: string): boolean {
  return expandedMachines.value.has(`${resourceId}|${statusType}`);
}

function handleMachineEventMount(resourceId: string, statusType: string): void {
  emit('expand-machine', { resourceId, statusType });
}
</script>

<template>
  <div class="equipment-tier-table-wrap">
    <!-- Export toolbar -->
    <div class="detail-toolbar">
      <span class="section-title">設備明細（{{ equipmentRows.length }} 台）</span>
      <button
        type="button"
        class="export-btn"
        :disabled="exporting"
        @click="emit('export')"
      >
        {{ exporting ? '匯出中...' : '匯出 CSV' }}
      </button>
    </div>

    <!-- Loading overlay -->
    <div v-if="loading" class="loading-state" role="status" aria-label="載入中">
      載入中...
    </div>

    <table v-else class="tier-table">
      <thead>
        <tr>
          <th class="expand-col"></th>
          <th>設備名稱</th>
          <th>工作站</th>
          <th>機種</th>
          <th>小時數</th>
          <th>事件數</th>
          <th>主要原因</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="status in visibleGroups" :key="status">
          <!-- Tier 1: Status group header row -->
          <tr
            class="status-group-row"
            role="button"
            tabindex="0"
            :aria-expanded="expandedGroups.has(status)"
            @click="toggleGroup(status)"
            @keydown.enter.prevent="toggleGroup(status)"
            @keydown.space.prevent="toggleGroup(status)"
          >
            <td class="expand-toggle"><span :class="['toggle-icon', { 'toggle-icon--open': expandedGroups.has(status) }]">▶</span></td>
            <td colspan="3" class="status-group-label">
              <span :class="['status-badge', `badge-${status.toLowerCase()}`]">{{ status }}</span>
            </td>
            <td>{{ groupHours(status).toFixed(1) }}h</td>
            <td>
              {{ groupEventCount(status) }} 件
              <span v-if="groupMachineCount(status) > 50" class="top50-note">（顯示前50台）</span>
            </td>
            <td></td>
          </tr>

          <!-- Tier 2: Machine rows (when group expanded) -->
          <template v-if="expandedGroups.has(status)">
            <template
              v-for="machine in machinesForStatus(status)"
              :key="machine.resource_id"
            >
              <tr
                class="machine-row"
                role="button"
                tabindex="0"
                :aria-expanded="isMachineExpanded(machine.resource_id, status)"
                @click="toggleMachine(machine.resource_id, status)"
                @keydown.enter.prevent="toggleMachine(machine.resource_id, status)"
                @keydown.space.prevent="toggleMachine(machine.resource_id, status)"
              >
                <td class="expand-toggle expand-machine-toggle"><span :class="['toggle-icon', { 'toggle-icon--open': isMachineExpanded(machine.resource_id, status) }]">▶</span></td>
                <td>{{ machine.resource_name ?? machine.resource_id }}</td>
                <td>{{ machine.workcenter ?? '—' }}</td>
                <td>{{ machine.family ?? '—' }}</td>
                <td>{{ machineStatusHours(machine, status).toFixed(2) }}h</td>
                <td>{{ machineStatusEventCount(machine, status) }}</td>
                <td>{{ machine.top_reason ?? '—' }}</td>
              </tr>

              <!-- Tier 3: Events (when machine expanded, lazy-loaded) -->
              <tr
                v-if="isMachineExpanded(machine.resource_id, status)"
                class="tier3-events-row"
              >
                <td colspan="7" class="tier3-events-cell">
                  <MachineEventRows
                    :cache-entry="tierThreeCache[`${machine.resource_id}|${status}`]"
                    @mount="handleMachineEventMount(machine.resource_id, status)"
                  />
                </td>
              </tr>
            </template>
          </template>
        </template>

        <!-- Empty state when no equipment rows -->
        <tr v-if="!loading && equipmentRows.length === 0">
          <td colspan="7" class="empty-state">暫無資料</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
