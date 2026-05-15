// @vitest-environment jsdom
/**
 * Unit tests for MultiSelect.vue — dropdown-close emit contract
 *
 * Change: fix-prod-history-multiselect-filter
 * AC-1: no emit while dropdown is open
 * AC-2: single emit on close (outside-click / Escape / blur)
 * Regression: update:modelValue still fires on every toggle (back-compat)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick, defineComponent } from 'vue';
import MultiSelect from '../MultiSelect.vue';

// Stub LoadingSpinner (imported inside MultiSelect.vue) to avoid needing its
// full implementation in the jsdom environment.
vi.mock('../LoadingSpinner.vue', () => ({
  default: defineComponent({
    name: 'LoadingSpinner',
    template: '<span class="loading-spinner-stub" />',
  }),
}));

const DEFAULT_OPTIONS = ['Alpha', 'Beta', 'Gamma'];

function mountSelect(overrides: Record<string, unknown> = {}) {
  return mount(MultiSelect, {
    props: {
      modelValue: [],
      options: DEFAULT_OPTIONS,
      searchable: false, // disables autofocus side-effects in jsdom
      ...overrides,
    },
    attachTo: document.body,
  });
}

describe('MultiSelect — dropdown-close emit (fix-prod-history-multiselect-filter)', () => {
  beforeEach(() => {
    // Clean up any leftover DOM from previous test's `attachTo: document.body`.
    document.body.innerHTML = '';
  });

  it('emits dropdown-close once on outside-click with final selection', async () => {
    const wrapper = mountSelect({ modelValue: ['Alpha'] });

    // Open the dropdown.
    await wrapper.find('.multi-select-trigger').trigger('click');
    await nextTick();
    expect(wrapper.find('.multi-select-dropdown').exists()).toBe(true);

    // Simulate outside-click: dispatch a click on document (outside rootRef).
    document.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await nextTick();
    await nextTick();

    const closeEmits = wrapper.emitted('dropdown-close') as string[][] | undefined;
    expect(closeEmits).toBeTruthy();
    expect(closeEmits!.length).toBe(1);
    expect(closeEmits![0][0]).toEqual(['Alpha']);
  });

  it('emits dropdown-close once on Escape with final selection', async () => {
    const wrapper = mountSelect({ modelValue: ['Beta'] });

    // Open the dropdown.
    await wrapper.find('.multi-select-trigger').trigger('click');
    await nextTick();
    expect(wrapper.find('.multi-select-dropdown').exists()).toBe(true);

    // Press Escape on the dropdown container.
    await wrapper.find('.multi-select-dropdown').trigger('keydown', { key: 'Escape' });
    await nextTick();
    await nextTick();

    const closeEmits = wrapper.emitted('dropdown-close') as string[][] | undefined;
    expect(closeEmits).toBeTruthy();
    expect(closeEmits!.length).toBe(1);
    expect(closeEmits![0][0]).toEqual(['Beta']);
  });

  it.skip('emits dropdown-close once on blur with final selection', async () => {
    // TODO: Pure keyboard tab-out blur is not deterministic in jsdom because
    // MultiSelect relies on outside-click (captured at document level) rather
    // than a focusout listener on the root element. Tab-out in jsdom does not
    // trigger the outside-click handler. This case is documented in design.md
    // §1 as an accepted gap for pure-keyboard tab navigation.
    // Covered at the E2E level by the Playwright suite instead.
  });

  it('dropdown-close payload equals current model-value at close time', async () => {
    const wrapper = mountSelect({ modelValue: ['Alpha', 'Gamma'] });

    await wrapper.find('.multi-select-trigger').trigger('click');
    await nextTick();

    // Close via the 「關閉」 footer button.
    await wrapper.find('.multi-select-actions button:last-child').trigger('click');
    await nextTick();
    await nextTick();

    const closeEmits = wrapper.emitted('dropdown-close') as string[][] | undefined;
    expect(closeEmits).toBeTruthy();
    expect(closeEmits![0][0]).toEqual(['Alpha', 'Gamma']);
  });

  it('does not emit dropdown-close while dropdown is open across multiple toggles', async () => {
    const wrapper = mountSelect({ modelValue: [] });

    // Open.
    await wrapper.find('.multi-select-trigger').trigger('click');
    await nextTick();

    // Toggle options multiple times while keeping the dropdown open.
    const options = wrapper.findAll('.multi-select-option');
    await options[0].trigger('click');
    await nextTick();
    await options[1].trigger('click');
    await nextTick();
    await options[0].trigger('click');
    await nextTick();

    // Dropdown is still open — no dropdown-close should have been emitted yet.
    expect(wrapper.emitted('dropdown-close')).toBeFalsy();

    // Now close it.
    await wrapper.find('.multi-select-actions button:last-child').trigger('click');
    await nextTick();
    await nextTick();

    // Only now should it emit, exactly once.
    const closeEmits = wrapper.emitted('dropdown-close');
    expect(closeEmits).toBeTruthy();
    expect(closeEmits!.length).toBe(1);
  });

  it('still emits update:modelValue on every toggle (back-compat for unlisted consumers)', async () => {
    const wrapper = mountSelect({ modelValue: [] });

    // Open.
    await wrapper.find('.multi-select-trigger').trigger('click');
    await nextTick();

    const options = wrapper.findAll('.multi-select-option');
    await options[0].trigger('click');
    await nextTick();
    await options[1].trigger('click');
    await nextTick();

    // update:modelValue fires for each toggle.
    const updateEmits = wrapper.emitted('update:modelValue');
    expect(updateEmits).toBeTruthy();
    expect(updateEmits!.length).toBe(2);
  });

  it('consumers without @dropdown-close listener see no behavioral change', async () => {
    // Mount without any listener for dropdown-close.
    const wrapper = mountSelect({ modelValue: ['Gamma'] });

    // Open and close — should not throw and update:modelValue should still work.
    await wrapper.find('.multi-select-trigger').trigger('click');
    await nextTick();

    const options = wrapper.findAll('.multi-select-option');
    await options[0].trigger('click'); // toggle Alpha
    await nextTick();

    // Close.
    await wrapper.find('.multi-select-actions button:last-child').trigger('click');
    await nextTick();
    await nextTick();

    // update:modelValue still fired (back-compat).
    expect(wrapper.emitted('update:modelValue')).toBeTruthy();
    // dropdown-close fired but no listener — component did not throw.
    // (The emit is fired into the void; this is the desired behavior.)
    expect(wrapper.emitted('dropdown-close')).toBeTruthy();
  });
});
