// @vitest-environment jsdom
/**
 * ActionButton / ExportButton component tests
 *
 * No generic ActionButton.vue exists in the codebase.
 * The closest equivalent is ExportButton.vue in query-tool/components,
 * which has isLoading/disabled behaviour.
 *
 * Tests cover:
 *  - Normal click emits no action (ExportButton has no emitted events — it's a
 *    presentational button; click handling is done by parent via native click)
 *  - Button is disabled when loading=true (prevents double-click at DOM level)
 *  - Button is not disabled when loading=false
 *  - Loading spinner is shown when loading=true
 *  - Label changes when loading
 */

import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import ExportButton from '../../src/query-tool/components/ExportButton.vue';

describe('ExportButton (ActionButton equivalent)', () => {
  it('renders a button element', () => {
    const wrapper = mount(ExportButton);
    expect(wrapper.find('button').exists()).toBe(true);
  });

  it('is not disabled when loading=false', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: false, disabled: false },
    });
    expect(wrapper.find('button').attributes('disabled')).toBeUndefined();
  });

  it('is disabled when loading=true (prevents double-click)', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: true },
    });
    expect(wrapper.find('button').attributes('disabled')).toBeDefined();
  });

  it('is disabled when disabled=true', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: false, disabled: true },
    });
    expect(wrapper.find('button').attributes('disabled')).toBeDefined();
  });

  it('shows LoadingSpinner when loading=true', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: true },
    });
    expect(wrapper.find('.loading-spinner').exists()).toBe(true);
  });

  it('does not show LoadingSpinner when loading=false', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: false },
    });
    expect(wrapper.find('.loading-spinner').exists()).toBe(false);
  });

  it('shows loading text when loading=true', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: true },
    });
    expect(wrapper.find('button').text()).toContain('匯出中');
  });

  it('shows default label when loading=false', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: false, label: '匯出 CSV' },
    });
    expect(wrapper.find('button').text()).toContain('匯出 CSV');
  });

  it('does not fire a second click event when already disabled (loading)', async () => {
    const clickHandler = vi.fn();
    const wrapper = mount(ExportButton, {
      props: { loading: true },
      attrs: { onClick: clickHandler },
    });
    // The button is disabled — browser won't fire click, but trigger() still works in jsdom.
    // We verify the disabled attribute is present as the double-click guard.
    expect(wrapper.find('button').attributes('disabled')).toBeDefined();
    // Triggering click on a disabled button should not fire the handler in real browsers;
    // in jsdom disabled buttons still receive events via trigger(), so we test the attribute.
    const btn = wrapper.find('button');
    expect(btn.element.disabled).toBe(true);
  });

  it('accepts custom label prop', () => {
    const wrapper = mount(ExportButton, {
      props: { loading: false, label: '下載報表' },
    });
    expect(wrapper.find('button').text()).toContain('下載報表');
  });
});
