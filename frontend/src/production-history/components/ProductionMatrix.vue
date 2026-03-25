<script setup>
import { ref } from 'vue';

const props = defineProps({
  tree: { type: Array, default: () => [] },
  monthColumns: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  activeFilter: { type: Object, default: () => ({}) },
});

const emit = defineEmits(['select-node', 'clear-filter']);

// Track expanded nodes
const expandedWc = ref(new Set());
const expandedSpec = ref(new Set());

function toggleWc(label) {
  expandedWc.value.has(label) ? expandedWc.value.delete(label) : expandedWc.value.add(label);
}

function toggleSpec(wcLabel, specLabel) {
  const key = `${wcLabel}::${specLabel}`;
  expandedSpec.value.has(key) ? expandedSpec.value.delete(key) : expandedSpec.value.add(key);
}

function selectNode(level, filter) {
  emit('select-node', { level, filter });
}

function isActiveWc(label) {
  return props.activeFilter.workcenter_group === label && !props.activeFilter.spec && !props.activeFilter.equipment_id;
}

function isActiveSpec(wcLabel, specLabel) {
  return props.activeFilter.workcenter_group === wcLabel &&
    props.activeFilter.spec === specLabel && !props.activeFilter.equipment_id;
}

function isActiveEqp(eqpId) {
  return props.activeFilter.equipment_id === eqpId;
}

const hasActiveFilter = () =>
  !!(props.activeFilter.workcenter_group || props.activeFilter.spec || props.activeFilter.equipment_id);
</script>

<template>
  <div class="ui-card">
    <div class="ui-card-header">
      <span class="ui-card-title">聚合 Matrix</span>
    </div>

    <div class="ui-card-body">
      <div v-if="loading" class="placeholder">載入中…</div>

      <div v-else-if="!tree.length" class="placeholder">無資料</div>

      <div v-else class="detail-table-wrap">
        <table class="detail-table ph-matrix-table">
          <thead>
            <tr>
              <th class="ph-matrix-label-col">WorkCenter Group / Spec / Equipment</th>
              <th class="ph-matrix-count-col">合計</th>
              <th
                v-for="month in monthColumns"
                :key="month"
                class="ph-matrix-month-col"
              >
                {{ month }}
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="wcNode in tree" :key="wcNode.label">
              <!-- WorkCenter Group row -->
              <tr
                class="ph-matrix-row ph-matrix-row--wc"
                :class="{ 'ph-matrix-row--active': isActiveWc(wcNode.label) }"
                @click="selectNode('workcenter', { workcenter_group: wcNode.label, spec: '' })"
              >
                <td class="ph-matrix-label-cell">
                  <button
                    class="ph-matrix-expand"
                    @click.stop="toggleWc(wcNode.label)"
                  >
                    {{ expandedWc.has(wcNode.label) ? '&#9660;' : '&#9654;' }}
                  </button>
                  <span class="ph-matrix-wc-label">{{ wcNode.label }}</span>
                </td>
                <td class="ph-matrix-num-cell">{{ wcNode.count }}</td>
                <td
                  v-for="month in monthColumns"
                  :key="month"
                  class="ph-matrix-num-cell"
                >
                  {{ wcNode.month_counts?.[month] || '' }}
                </td>
              </tr>

              <!-- Spec rows (shown when wc is expanded) -->
              <template v-if="expandedWc.has(wcNode.label)">
                <template v-for="specNode in wcNode.children" :key="specNode.label">
                  <tr
                    class="ph-matrix-row ph-matrix-row--spec"
                    :class="{ 'ph-matrix-row--active': isActiveSpec(wcNode.label, specNode.label) }"
                    @click.stop="selectNode('spec', { workcenter_group: wcNode.label, spec: specNode.label, equipment_id: '' })"
                  >
                    <td class="ph-matrix-label-cell ph-matrix-indent">
                      <button
                        class="ph-matrix-expand"
                        @click.stop="toggleSpec(wcNode.label, specNode.label)"
                      >
                        {{ expandedSpec.has(`${wcNode.label}::${specNode.label}`) ? '&#9660;' : '&#9654;' }}
                      </button>
                      <span class="ph-matrix-spec-label">{{ specNode.label }}</span>
                    </td>
                    <td class="ph-matrix-num-cell">{{ specNode.count }}</td>
                    <td
                      v-for="month in monthColumns"
                      :key="month"
                      class="ph-matrix-num-cell"
                    >
                      {{ specNode.month_counts?.[month] || '' }}
                    </td>
                  </tr>

                  <!-- Equipment rows (shown when spec is expanded) -->
                  <template v-if="expandedSpec.has(`${wcNode.label}::${specNode.label}`)">
                    <tr
                      v-for="eqpNode in specNode.children"
                      :key="eqpNode.label"
                      class="ph-matrix-row ph-matrix-row--eqp"
                      :class="{ 'ph-matrix-row--active': isActiveEqp(eqpNode.label) }"
                      @click.stop="selectNode('equipment', { workcenter_group: wcNode.label, spec: specNode.label, equipment_id: eqpNode.label })"
                    >
                      <td class="ph-matrix-label-cell ph-matrix-indent-2">
                        <span class="ph-matrix-eqp-label">{{ eqpNode.equipment_name || eqpNode.label }}</span>
                      </td>
                      <td class="ph-matrix-num-cell">{{ eqpNode.count }}</td>
                      <td
                        v-for="month in monthColumns"
                        :key="month"
                        class="ph-matrix-num-cell"
                      >
                        {{ eqpNode.month_counts?.[month] || '' }}
                      </td>
                    </tr>
                  </template>
                </template>
              </template>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Filter chip -->
      <div v-if="hasActiveFilter()" class="ph-matrix-chip">
        <span>已篩選：
          <template v-if="activeFilter.workcenter_group">{{ activeFilter.workcenter_group }}</template>
          <template v-if="activeFilter.spec"> / {{ activeFilter.spec }}</template>
          <template v-if="activeFilter.equipment_id"> / {{ activeFilter.equipment_id }}</template>
        </span>
        <button class="ui-btn ui-btn--sm" @click="emit('clear-filter')">清除篩選</button>
      </div>
    </div>
  </div>
</template>
