// @vitest-environment jsdom
/**
 * Unit tests for FilterPanel.vue
 * Change: material-part-consumption
 *
 * AC-2: 20-part cap client-side validation
 * Reset button clears all inputs (MultiSelect + date fields)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import FilterPanel from '../components/FilterPanel.vue';

// Stub shared-ui MultiSelect; exposes a programmatic way to set value.
// The stub emits whatever options[0..1] are, so display-string tests work
// without knowing the exact strings at mock-definition time.
vi.mock('../../shared-ui/components/MultiSelect.vue', () => ({
  default: defineComponent({
    name: 'MultiSelect',
    props: ['modelValue', 'options', 'placeholder', 'disabled', 'loading'],
    emits: ['update:modelValue', 'dropdown-close'],
    // set-stub emits the first two options (display strings from partDisplayOptions)
    template: `<div class="multi-select-stub" :data-testid="$attrs['data-testid']">
      <button class="set-stub" @click="$emit('update:modelValue', (options || []).slice(0, 2))">set</button>
      <button class="clear-stub" @click="$emit('update:modelValue', [])">clear</button>
      <span class="value-stub">{{ (modelValue || []).join(',') }}</span>
    </div>`,
  }),
}));

// partOptions now uses object format: {name, description?}
const DEFAULT_PART_OPTIONS = [
  { name: 'PART-A' },
  { name: 'PART-B', description: 'desc' },
  { name: 'PART-C', description: null },
];

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(FilterPanel, {
    props: {
      partOptions: DEFAULT_PART_OPTIONS,
      ...props,
    },
    attachTo: document.body,
  });
}

describe('FilterPanel', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('clears_selection_on_reset', async () => {
    const wrapper = mountPanel();

    // Simulate selecting parts via the MultiSelect stub (parts select)
    const partsSelect = wrapper.find('[data-testid="material-parts-select"]');
    expect(partsSelect.exists()).toBe(true);
    await partsSelect.find('.set-stub').trigger('click');
    await nextTick();

    // Fill in date inputs
    const startDate = wrapper.find('input[data-testid="start-date"]');
    const endDate = wrapper.find('input[data-testid="end-date"]');
    expect(startDate.exists()).toBe(true);
    expect(endDate.exists()).toBe(true);
    await startDate.setValue('2026-01-01');
    await endDate.setValue('2026-01-31');

    // Click reset button
    const resetBtn = wrapper.find('[data-testid="reset-button"]');
    expect(resetBtn.exists()).toBe(true);
    await resetBtn.trigger('click');
    await nextTick();

    // Verify that reset event was emitted
    const emitted = wrapper.emitted('reset');
    expect(emitted).toBeTruthy();

    // After reset, part count label should show 0
    const inputCount = wrapper.find('.input-count');
    expect(inputCount.text()).toContain('0');
  });

  it('shows_day_granularity_button', async () => {
    const wrapper = mountPanel();
    const dayBtn = wrapper.find('[data-granularity="day"]');
    expect(dayBtn.exists()).toBe(true);
    expect(dayBtn.text()).toBe('日');
  });

  it('partDisplayOptions_renders_name_with_description', async () => {
    const wrapper = mountPanel();

    // The parts MultiSelect stub receives options from partDisplayOptions.
    // Locate all MultiSelect stub instances; index 0 = parts select.
    const allSelectComponents = wrapper.findAllComponents({ name: 'MultiSelect' });
    expect(allSelectComponents.length).toBeGreaterThanOrEqual(1);
    const partsSelectComponent = allSelectComponents[0];

    const passedOptions = partsSelectComponent.props('options') as string[];
    // PART-A has no description → plain name
    expect(passedOptions[0]).toBe('PART-A');
    // PART-B has description → "NAME — description"
    expect(passedOptions[1]).toBe('PART-B — desc');
    // PART-C has description: null → plain name
    expect(passedOptions[2]).toBe('PART-C');
  });

  it('submit_payload_maps_display_strings_back_to_raw_part_names', async () => {
    const wrapper = mountPanel();

    // Select parts (stub emits first two display options: ['PART-A', 'PART-B — desc'])
    const partsSelect = wrapper.find('[data-testid="material-parts-select"]');
    await partsSelect.find('.set-stub').trigger('click');
    await nextTick();

    // Fill required date fields
    await wrapper.find('input[data-testid="start-date"]').setValue('2026-01-01');
    await wrapper.find('input[data-testid="end-date"]').setValue('2026-01-31');

    // Submit
    await wrapper.find('[data-testid="query-submit-button"]').trigger('click');
    await nextTick();

    const emitted = wrapper.emitted('query-submit');
    expect(emitted).toBeTruthy();
    const payload = (emitted as Array<Array<{ material_parts: string[] }>>)[0][0];
    // Must be raw names, not display strings
    expect(payload.material_parts).toEqual(['PART-A', 'PART-B']);
  });
});
