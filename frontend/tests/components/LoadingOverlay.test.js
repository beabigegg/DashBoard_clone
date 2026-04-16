// @vitest-environment jsdom
/**
 * LoadingOverlay component tests
 *
 * Props:
 *   tier: 'page' | 'section' (default: 'section')
 *
 * The overlay div gets class `loading-overlay--${tier}`.
 * When tier='page' it renders LoadingSpinner size='lg', otherwise 'md'.
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import LoadingOverlay from '../../src/shared-ui/components/LoadingOverlay.vue';

describe('LoadingOverlay', () => {
  it('renders with default tier=section', () => {
    const wrapper = mount(LoadingOverlay);
    expect(wrapper.find('.loading-overlay').exists()).toBe(true);
    expect(wrapper.find('.loading-overlay--section').exists()).toBe(true);
    expect(wrapper.find('.loading-overlay--page').exists()).toBe(false);
  });

  it('renders with tier=page class', () => {
    const wrapper = mount(LoadingOverlay, {
      props: { tier: 'page' },
    });
    expect(wrapper.find('.loading-overlay--page').exists()).toBe(true);
    expect(wrapper.find('.loading-overlay--section').exists()).toBe(false);
  });

  it('renders with tier=section class', () => {
    const wrapper = mount(LoadingOverlay, {
      props: { tier: 'section' },
    });
    expect(wrapper.find('.loading-overlay--section').exists()).toBe(true);
  });

  it('contains a loading spinner child', () => {
    const wrapper = mount(LoadingOverlay, {
      props: { tier: 'page' },
    });
    // LoadingSpinner renders a span.loading-spinner
    expect(wrapper.find('.loading-spinner').exists()).toBe(true);
  });

  it('spinner has role=status for accessibility', () => {
    const wrapper = mount(LoadingOverlay, {
      props: { tier: 'section' },
    });
    const spinner = wrapper.find('[role="status"]');
    expect(spinner.exists()).toBe(true);
  });
});
