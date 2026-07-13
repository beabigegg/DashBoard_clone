// @vitest-environment jsdom
/**
 * Unit tests for the additive `message` override prop on EmptyState.vue.
 *
 * Added by add-uph-performance-page: several existing consumers already pass
 * `message="..."` expecting custom text, which was previously a silently
 * dropped fallthrough attribute (never rendered) because `message` was not a
 * declared prop. This locks in that fix without changing the default
 * (no-`message`) behavior any existing consumer relies on.
 */
import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import EmptyState from '../EmptyState.vue';

describe('EmptyState', () => {
  it('renders the canned per-type message when no message prop is given (unchanged default)', () => {
    const wrapper = mount(EmptyState, { props: { type: 'no-data' } });
    expect(wrapper.text()).toContain('目前沒有資料');
  });

  it('renders the caller-supplied message verbatim when provided, overriding the canned text', () => {
    const wrapper = mount(EmptyState, {
      props: { type: 'no-data', message: '此範圍無 UPH 資料，請放寬日期或調整篩選器' },
    });
    expect(wrapper.text()).toContain('此範圍無 UPH 資料，請放寬日期或調整篩選器');
    expect(wrapper.text()).not.toContain('目前沒有資料');
  });

  it('falls back to the filter-empty canned message when message is an empty string', () => {
    const wrapper = mount(EmptyState, { props: { type: 'filter-empty', message: '' } });
    expect(wrapper.text()).toContain('找不到符合條件的資料');
  });
});
