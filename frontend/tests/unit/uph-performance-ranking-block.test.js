// @vitest-environment jsdom
/**
 * Component tests for RankingBlock.vue
 *
 * Validates interaction-design.md §Confirmed #2 / #7 and the ranking block's
 * three sub-states: no-selection prompt, empty result, populated table.
 */
import { describe, it, expect } from 'vitest';
import { defineComponent } from 'vue';
import { mount } from '@vue/test-utils';

import RankingBlock from '../../src/uph-performance/RankingBlock.vue';

const MultiSelectStub = defineComponent({
  name: 'MultiSelect',
  props: {
    modelValue: { type: Array, default: () => [] },
    options: { type: Array, default: () => [] },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div class="multi-select-stub">{{ (modelValue || []).join(",") }}</div>',
});

function mountRanking(props) {
  return mount(RankingBlock, {
    props,
    global: { stubs: { MultiSelect: MultiSelectStub } },
  });
}

describe('RankingBlock', () => {
  it('shows a selection-prompt (not an error) when no Type is selected — confirmed #2', () => {
    const wrapper = mountRanking({ items: [], typeOptions: ['TYPE-A'], selectedTypes: [], loading: false });
    expect(wrapper.find('[data-testid="ranking-prompt"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="ranking-empty"]').exists()).toBe(false);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });

  it('shows the generic empty-state wording (no BondUPH/fHCM_UPH leak) once a Type is selected but items is empty', () => {
    const wrapper = mountRanking({ items: [], typeOptions: ['TYPE-A'], selectedTypes: ['TYPE-A'], loading: false });
    const empty = wrapper.find('[data-testid="ranking-empty"]');
    expect(empty.exists()).toBe(true);
    expect(empty.text()).toContain('此範圍無 UPH 資料，請放寬日期或調整篩選器');
    expect(empty.text()).not.toContain('BondUPH');
    expect(empty.text()).not.toContain('fHCM_UPH');
  });

  it('renders ranked rows once a Type is selected and items is populated', async () => {
    const wrapper = mountRanking({
      items: [
        { equipment_id: 'GDBA-001', workcenter_name: 'WC-1', db_wb_label: '焊接_DB', pj_type: 'TYPE-A', avg_uph: 12.5, sample_count: 20 },
      ],
      typeOptions: ['TYPE-A'],
      selectedTypes: ['TYPE-A'],
      loading: false,
    });
    // DataTableColumn registers its column via onMounted (child-mount timing);
    // flush one tick so DataTable's reactive `columns` ref reflects them.
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-testid="ranking-prompt"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('GDBA-001');
    expect(wrapper.text()).toContain('焊接_DB');
  });

  it('renders "—" (not null/undefined) when db_wb_label is null for a row (confirmed #7)', async () => {
    const wrapper = mountRanking({
      items: [
        { equipment_id: 'GWBA-009', workcenter_name: null, db_wb_label: null, pj_type: null, avg_uph: null, sample_count: 0 },
      ],
      typeOptions: ['TYPE-A'],
      selectedTypes: ['TYPE-A'],
      loading: false,
    });
    await wrapper.vm.$nextTick();
    const text = wrapper.text();
    expect(text).toContain('GWBA-009');
    expect(text).not.toContain('null');
    expect(text).not.toContain('undefined');
  });

  it('emits update:selectedTypes from its own MultiSelect without touching any global filter state', async () => {
    const wrapper = mountRanking({ items: [], typeOptions: ['TYPE-A', 'TYPE-B'], selectedTypes: [], loading: false });
    const select = wrapper.findComponent(MultiSelectStub);
    await select.vm.$emit('update:modelValue', ['TYPE-B']);
    expect(wrapper.emitted('update:selectedTypes')).toBeTruthy();
    expect(wrapper.emitted('update:selectedTypes')[0][0]).toEqual(['TYPE-B']);
  });
});
