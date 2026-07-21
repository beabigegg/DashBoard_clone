// @vitest-environment jsdom
/**
 * Unit tests for FilterPanel.vue (equipment-lookup / 機台查詢)
 *
 * 3 independent MultiSelects (機台位置/機型/編號) — no cross-filter narrowing;
 * query-submit always allowed (all 3 filters optional — quick lookup tool);
 * reset clears all 3 selections and re-emits reset.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent } from 'vue';
import FilterPanel from '../components/FilterPanel.vue';

vi.mock('../../shared-ui/components/MultiSelect.vue', () => ({
  default: defineComponent({
    name: 'MultiSelect',
    props: ['modelValue', 'options', 'placeholder', 'disabled', 'searchable'],
    emits: ['update:modelValue'],
    template: `<div class="multi-select-stub" :data-testid="$attrs['data-testid']">
      <button class="set-stub" @click="$emit('update:modelValue', (options || []).slice(0, 1))">set</button>
      <span class="value-stub">{{ (modelValue || []).join(',') }}</span>
    </div>`,
  }),
}));

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(FilterPanel, {
    props: {
      locationOptions: ['LOC-A', 'LOC-B'],
      familyOptions: ['FAM-A'],
      resourceNameOptions: ['R001', 'R002'],
      ...props,
    },
    attachTo: document.body,
  });
}

describe('FilterPanel (equipment-lookup)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('renders_all_3_independent_filters', () => {
    const wrapper = mountPanel();
    expect(wrapper.find('[data-testid="location-select"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="family-select"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="resource-name-select"]').exists()).toBe(true);
  });

  it('resource_name_select_is_searchable', () => {
    const wrapper = mountPanel();
    const resourceNameSelect = wrapper
      .findAllComponents({ name: 'MultiSelect' })
      .find((c) => c.attributes('data-testid') === 'resource-name-select');
    expect(resourceNameSelect?.props('searchable')).toBe(true);
  });

  it('submits_with_no_filters_selected_all_optional', async () => {
    const wrapper = mountPanel();
    await wrapper.find('[data-testid="query-submit-button"]').trigger('click');

    const emitted = wrapper.emitted('query-submit');
    expect(emitted).toBeTruthy();
    const payload = (emitted as Array<Array<Record<string, string[]>>>)[0][0];
    expect(payload).toEqual({ locations: [], families: [], resource_names: [] });
  });

  it('submits_each_filter_axis_independently', async () => {
    const wrapper = mountPanel();

    await wrapper.find('[data-testid="location-select"] .set-stub').trigger('click');
    await wrapper.find('[data-testid="query-submit-button"]').trigger('click');

    const payload = (wrapper.emitted('query-submit') as Array<Array<Record<string, string[]>>>)[0][0];
    expect(payload.locations).toEqual(['LOC-A']);
    expect(payload.families).toEqual([]);
    expect(payload.resource_names).toEqual([]);
  });

  it('clears_all_selections_and_emits_reset', async () => {
    const wrapper = mountPanel();

    await wrapper.find('[data-testid="location-select"] .set-stub').trigger('click');
    await wrapper.find('[data-testid="family-select"] .set-stub').trigger('click');
    await wrapper.find('[data-testid="resource-name-select"] .set-stub').trigger('click');

    await wrapper.find('[data-testid="reset-button"]').trigger('click');

    expect(wrapper.emitted('reset')).toBeTruthy();

    await wrapper.find('[data-testid="query-submit-button"]').trigger('click');
    const payload = (wrapper.emitted('query-submit') as Array<Array<Record<string, string[]>>>)[0][0];
    expect(payload).toEqual({ locations: [], families: [], resource_names: [] });
  });

  it('disables_submit_button_while_loading', () => {
    const wrapper = mountPanel({ loading: true });
    const btn = wrapper.find('[data-testid="query-submit-button"]');
    expect(btn.attributes('disabled')).toBeDefined();
    expect(btn.text()).toBe('查詢中...');
  });
});
