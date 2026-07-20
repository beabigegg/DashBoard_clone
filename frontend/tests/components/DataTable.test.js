// @vitest-environment jsdom
/**
 * DataTable component tests
 *
 * DataTable uses a column-registry pattern via provide/inject.
 * Columns are registered by DataTableColumn children.
 * Tests verify resilient rendering without crashing on edge-case props.
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import { h, ref } from 'vue';
import DataTable from '../../src/shared-ui/components/DataTable.vue';
import DataTableColumn from '../../src/shared-ui/components/DataTableColumn.vue';

describe('DataTable', () => {
  it('renders without crash when data is empty', () => {
    const wrapper = mount(DataTable, {
      props: { data: [] },
    });
    expect(wrapper.exists()).toBe(true);
    // Empty state should appear
    expect(wrapper.find('.data-table-root').exists()).toBe(true);
  });

  it('shows loading class when loading=true', () => {
    const wrapper = mount(DataTable, {
      props: { data: [], loading: true },
    });
    expect(wrapper.find('.data-table-scroll').classes()).toContain('is-loading');
  });

  it('does not have loading class when loading=false', () => {
    const wrapper = mount(DataTable, {
      props: { data: [{ id: 1 }], loading: false },
    });
    expect(wrapper.find('.data-table-scroll').classes()).not.toContain('is-loading');
  });

  it('renders without crash when pagination has NaN page', () => {
    // NaN page should not crash PaginationControl (it falls back via || 1)
    const wrapper = mount(DataTable, {
      props: {
        data: [],
        pagination: { page: NaN, totalPages: 1, infoText: '' },
      },
    });
    expect(wrapper.exists()).toBe(true);
    expect(wrapper.find('.data-table-footer').exists()).toBe(true);
  });

  it('renders without crash with undefined data', () => {
    // default is [] so undefined should be coerced safely
    const wrapper = mount(DataTable, {
      props: { data: undefined },
    });
    expect(wrapper.exists()).toBe(true);
  });

  it('does not render pagination footer when pagination prop is null', () => {
    const wrapper = mount(DataTable, {
      props: { data: [], pagination: null },
    });
    expect(wrapper.find('.data-table-footer').exists()).toBe(false);
  });

  it('renders data rows when data is provided (no registered columns)', () => {
    // Without DataTableColumn children, columns array is empty,
    // but the component should not crash with row data.
    const wrapper = mount(DataTable, {
      props: { data: [{ name: 'A' }, { name: 'B' }] },
    });
    expect(wrapper.exists()).toBe(true);
    // isEmpty is false because data.length > 0, so first tbody is rendered
    const tbodies = wrapper.findAll('tbody');
    expect(tbodies.length).toBeGreaterThan(0);
  });

  it('updates the header text when a DataTableColumn label prop changes after mount', async () => {
    // Regression test: registerColumn used to fire only in onMounted, so a
    // dynamically computed label (e.g. switching 產出/轉出 modes) froze at
    // whatever it was on first render instead of tracking the new value.
    const label = ref('D班產出 (K)');
    const wrapper = mount({
      components: { DataTable, DataTableColumn },
      setup() {
        return { label };
      },
      render() {
        return h(DataTable, { data: [{ qty: 1 }] }, () => [
          h(DataTableColumn, { columnKey: 'qty', label: this.label }),
        ]);
      },
    });

    await wrapper.vm.$nextTick();
    expect(wrapper.find('.data-table-th').text()).toContain('D班產出 (K)');

    label.value = 'D班轉出 (K)';
    await wrapper.vm.$nextTick();

    expect(wrapper.find('.data-table-th').text()).toContain('D班轉出 (K)');
  });
});
