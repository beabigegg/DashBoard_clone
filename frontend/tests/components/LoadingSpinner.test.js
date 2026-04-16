// @vitest-environment jsdom
/**
 * LoadingSpinner component tests
 *
 * Props:
 *   size: 'sm' | 'md' | 'lg' (default: 'md')
 *
 * Renders a <span class="loading-spinner"> with inline size styles.
 * Has role="status" and aria-label="載入中".
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import LoadingSpinner from '../../src/shared-ui/components/LoadingSpinner.vue';

const SIZE_MAP = {
  sm: { diameter: '14px', border: '2px' },
  md: { diameter: '24px', border: '3px' },
  lg: { diameter: '42px', border: '4px' },
};

describe('LoadingSpinner', () => {
  it('renders a span with class loading-spinner', () => {
    const wrapper = mount(LoadingSpinner);
    expect(wrapper.find('span.loading-spinner').exists()).toBe(true);
  });

  it('has role=status for accessibility', () => {
    const wrapper = mount(LoadingSpinner);
    expect(wrapper.find('[role="status"]').exists()).toBe(true);
  });

  it('has aria-label attribute', () => {
    const wrapper = mount(LoadingSpinner);
    const span = wrapper.find('span.loading-spinner');
    expect(span.attributes('aria-label')).toBeTruthy();
  });

  it('renders sm size with correct inline styles', () => {
    const wrapper = mount(LoadingSpinner, { props: { size: 'sm' } });
    const span = wrapper.find('span.loading-spinner');
    expect(span.attributes('style')).toContain(SIZE_MAP.sm.diameter);
    expect(span.attributes('style')).toContain(SIZE_MAP.sm.border);
  });

  it('renders md size with correct inline styles', () => {
    const wrapper = mount(LoadingSpinner, { props: { size: 'md' } });
    const span = wrapper.find('span.loading-spinner');
    expect(span.attributes('style')).toContain(SIZE_MAP.md.diameter);
    expect(span.attributes('style')).toContain(SIZE_MAP.md.border);
  });

  it('renders lg size with correct inline styles', () => {
    const wrapper = mount(LoadingSpinner, { props: { size: 'lg' } });
    const span = wrapper.find('span.loading-spinner');
    expect(span.attributes('style')).toContain(SIZE_MAP.lg.diameter);
    expect(span.attributes('style')).toContain(SIZE_MAP.lg.border);
  });

  it('defaults to md when no size prop provided', () => {
    const wrapper = mount(LoadingSpinner);
    const span = wrapper.find('span.loading-spinner');
    expect(span.attributes('style')).toContain(SIZE_MAP.md.diameter);
  });
});
