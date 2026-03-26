<script setup>
import { ref } from 'vue';
import BlockLoadingState from '../../shared-ui/components/BlockLoadingState.vue';

const props = defineProps({
  tree: { type: Array, default: () => [] },
  monthColumns: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  activeFilter: { type: Object, default: () => ({}) },
});

const emit = defineEmits(['select-node', 'clear-filter']);

// Track expanded nodes (using Set for O(1) lookup)
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

function isActiveRow(wcLabel, specLabel, eqpId) {
  const f = props.activeFilter;
  if (!f.workcenter_group) return false;
  if (eqpId) return f.equipment_id === eqpId;
  if (specLabel) return f.workcenter_group === wcLabel && f.spec === specLabel && !f.equipment_id;
  return f.workcenter_group === wcLabel && !f.spec && !f.equipment_id;
}

function isActiveCell(wcLabel, specLabel, eqpId, month) {
  if (!isActiveRow(wcLabel, specLabel, eqpId)) return false;
  return props.activeFilter.month === month;
}

const hasActiveFilter = () =>
  !!(props.activeFilter.workcenter_group || props.activeFilter.spec || props.activeFilter.equipment_id);

function expandAll() {
  props.tree.forEach((wcNode) => {
    expandedWc.value.add(wcNode.label);
    (wcNode.children || []).forEach((specNode) => {
      expandedSpec.value.add(`${wcNode.label}::${specNode.label}`);
    });
  });
}

function collapseAll() {
  expandedWc.value.clear();
  expandedSpec.value.clear();
}
</script>

<template>
  <section class="section-card">
    <div class="section-inner">
      <div class="section-header">
        <h2 class="section-title">Workcenter x Equipment Matrix</h2>
        <div class="detail-toolbar">
          <button type="button" class="ui-btn ui-btn--sm" :disabled="loading" @click="expandAll">全部展開</button>
          <button type="button" class="ui-btn ui-btn--sm" :disabled="loading" @click="collapseAll">全部收合</button>
        </div>
      </div>

      <BlockLoadingState v-if="loading" />
      <div v-else-if="!tree.length" class="empty-state">無資料</div>

      <div v-else class="hierarchy-table-wrap">
        <table class="matrix-table">
          <thead>
            <tr>
              <th>Workcenter Group / Spec / Equipment</th>
              <th class="col-total">合計</th>
              <th
                v-for="month in monthColumns"
                :key="month"
              >
                {{ month }}
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="wcNode in tree" :key="wcNode.label">
              <!-- Workcenter Group row (level 0) -->
              <tr
                class="row-level-0 clickable-row"
                :class="{ selected: isActiveRow(wcNode.label, null, null) }"
                @click="selectNode('workcenter', { workcenter_group: wcNode.label })"
              >
                <td>
                  <span class="row-name">
                    <button
                      v-if="wcNode.children && wcNode.children.length"
                      type="button"
                      class="expand-btn"
                      :class="{ expanded: expandedWc.has(wcNode.label) }"
                      @click.stop="toggleWc(wcNode.label)"
                    >
                      ▶
                    </button>
                    <span v-else class="expand-placeholder"></span>
                    <span>{{ wcNode.label }}</span>
                  </span>
                </td>
                <td class="col-total">{{ wcNode.count }}</td>
                <td
                  v-for="month in monthColumns"
                  :key="month"
                  class="clickable-cell"
                  :class="{ 'cell-active': isActiveCell(wcNode.label, null, null, month) }"
                  @click.stop="selectNode('workcenter', { workcenter_group: wcNode.label, month })"
                >
                  {{ wcNode.month_counts?.[month] || '' }}
                </td>
              </tr>

              <!-- Spec rows (level 1, shown when wc is expanded) -->
              <template v-if="expandedWc.has(wcNode.label)">
                <template v-for="specNode in wcNode.children" :key="specNode.label">
                  <tr
                    class="row-level-1 indent-1 clickable-row"
                    :class="{ selected: isActiveRow(wcNode.label, specNode.label, null) }"
                    @click.stop="selectNode('spec', { workcenter_group: wcNode.label, spec: specNode.label })"
                  >
                    <td>
                      <span class="row-name">
                        <button
                          v-if="specNode.children && specNode.children.length"
                          type="button"
                          class="expand-btn"
                          :class="{ expanded: expandedSpec.has(`${wcNode.label}::${specNode.label}`) }"
                          @click.stop="toggleSpec(wcNode.label, specNode.label)"
                        >
                          ▶
                        </button>
                        <span v-else class="expand-placeholder"></span>
                        <span>{{ specNode.label }}</span>
                      </span>
                    </td>
                    <td class="col-total">{{ specNode.count }}</td>
                    <td
                      v-for="month in monthColumns"
                      :key="month"
                      class="clickable-cell"
                      :class="{ 'cell-active': isActiveCell(wcNode.label, specNode.label, null, month) }"
                      @click.stop="selectNode('spec', { workcenter_group: wcNode.label, spec: specNode.label, month })"
                    >
                      {{ specNode.month_counts?.[month] || '' }}
                    </td>
                  </tr>

                  <!-- Equipment rows (level 2, shown when spec is expanded) -->
                  <template v-if="expandedSpec.has(`${wcNode.label}::${specNode.label}`)">
                    <tr
                      v-for="eqpNode in specNode.children"
                      :key="eqpNode.label"
                      class="row-level-2 indent-2 clickable-row"
                      :class="{ selected: isActiveRow(wcNode.label, specNode.label, eqpNode.label) }"
                      @click.stop="selectNode('equipment', { workcenter_group: wcNode.label, spec: specNode.label, equipment_id: eqpNode.label })"
                    >
                      <td>
                        <span class="row-name">
                          <span class="expand-placeholder"></span>
                          <span>{{ eqpNode.equipment_name || eqpNode.label }}</span>
                        </span>
                      </td>
                      <td class="col-total">{{ eqpNode.count }}</td>
                      <td
                        v-for="month in monthColumns"
                        :key="month"
                        class="clickable-cell"
                        :class="{ 'cell-active': isActiveCell(wcNode.label, specNode.label, eqpNode.label, month) }"
                        @click.stop="selectNode('equipment', { workcenter_group: wcNode.label, spec: specNode.label, equipment_id: eqpNode.label, month })"
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
          <template v-if="activeFilter.month"> ({{ activeFilter.month }})</template>
        </span>
        <button class="ui-btn ui-btn--sm" @click="emit('clear-filter')">清除篩選</button>
      </div>
    </div>
  </section>
</template>
