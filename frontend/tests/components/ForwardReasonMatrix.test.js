// @vitest-environment jsdom
/**
 * ForwardReasonMatrix component tests (mid-section-defect)
 *
 * The component renders a correlation heat-table of:
 *   rows  = front-stage loss reasons
 *   cols  = downstream loss reasons
 *   cells = row_pct (default 占比 mode) or cells (數量 mode)
 *
 * Tests cover: renders, empty-state, mode toggle 占比/數量.
 */

import { describe, it, expect } from 'vitest';
import { mount } from '@vue/test-utils';
import ForwardReasonMatrix from '../../src/mid-section-defect/components/ForwardReasonMatrix.vue';

const SAMPLE_MATRIX = {
  rows: [
    { name: '043_NSOP', total: 28140 },
    { name: '044_NSOL', total: 15920 },
  ],
  cols: [
    { name: 'OPEN',  total: 18000 },
    { name: '短路',  total: 7000 },
    { name: '其他',  total: 5000 },
  ],
  cells: [
    [17447, 3377,  4783],
    [8756,  2866,  3024],
  ],
  row_pct: [
    [62, 12, 17],
    [55, 18, 19],
  ],
};

describe('ForwardReasonMatrix', () => {
  it('renders the table when matrix has rows and cols', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    expect(wrapper.find('[data-testid="matrix-table"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="matrix-empty"]').exists()).toBe(false);
  });

  it('shows the component title', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    expect(wrapper.text()).toContain('前段報廢原因 × 下游報廢原因 關聯');
  });

  it('renders front-stage reason rows (th[scope=row])', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    const rowHeaders = wrapper.findAll('tbody th[scope="row"]');
    expect(rowHeaders.length).toBe(2);
    expect(rowHeaders[0].text()).toBe('043_NSOP');
    expect(rowHeaders[1].text()).toBe('044_NSOL');
  });

  it('renders downstream reason columns (th[scope=col])', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    const colHeaders = wrapper.findAll('thead th[scope="col"]');
    // corner + 3 cols + total = 5
    expect(colHeaders.length).toBe(5);
    const colTexts = colHeaders.map((h) => h.text());
    expect(colTexts).toContain('OPEN');
    expect(colTexts).toContain('短路');
  });

  it('defaults to 占比 mode and shows percentage values', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    // Default is pct mode — cells should show N% format
    const tableText = wrapper.find('[data-testid="matrix-table"]').text();
    expect(tableText).toContain('62%');
    expect(tableText).toContain('55%');
  });

  it('toggles to 數量 mode and shows integer counts', async () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    const qtyBtn = wrapper.find('[data-testid="matrix-mode-qty"]');
    expect(qtyBtn.exists()).toBe(true);
    await qtyBtn.trigger('click');

    const tableText = wrapper.find('[data-testid="matrix-table"]').text();
    // Should contain localeString of a cell value (e.g., 17,447 or 17447)
    // Use regex to handle both forms across locales
    expect(/17[,.]?447|17447/.test(tableText)).toBe(true);
  });

  it('toggles back to 占比 mode after switching to 數量', async () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    await wrapper.find('[data-testid="matrix-mode-qty"]').trigger('click');
    await wrapper.find('[data-testid="matrix-mode-pct"]').trigger('click');

    const tableText = wrapper.find('[data-testid="matrix-table"]').text();
    expect(tableText).toContain('62%');
  });

  it('shows empty-state when matrix has no rows', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: { rows: [], cols: [], cells: [], row_pct: [] } },
    });
    expect(wrapper.find('[data-testid="matrix-empty"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="matrix-table"]').exists()).toBe(false);
  });

  it('shows empty-state when matrix prop is undefined', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: {},
    });
    expect(wrapper.find('[data-testid="matrix-empty"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="matrix-table"]').exists()).toBe(false);
  });

  it('shows empty-state when matrix prop is null', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: null },
    });
    expect(wrapper.find('[data-testid="matrix-empty"]').exists()).toBe(true);
  });

  it('shows row totals in the trailing total column', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    const tableText = wrapper.find('[data-testid="matrix-table"]').text();
    // Row totals from SAMPLE_MATRIX.rows
    expect(tableText).toContain(SAMPLE_MATRIX.rows[0].total.toLocaleString());
    expect(tableText).toContain(SAMPLE_MATRIX.rows[1].total.toLocaleString());
  });

  it('shows col totals in the trailing total row (tfoot)', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    const tfoot = wrapper.find('tfoot');
    expect(tfoot.exists()).toBe(true);
    const tfootText = tfoot.text();
    expect(tfootText).toContain(SAMPLE_MATRIX.cols[0].total.toLocaleString());
  });

  it('aria attributes are present for accessibility', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX },
    });
    // table must have aria-label
    const table = wrapper.find('table');
    expect(table.attributes('aria-label')).toBeTruthy();
    // col headers must have scope="col"
    const colThs = wrapper.findAll('thead th[scope="col"]');
    expect(colThs.length).toBeGreaterThan(1);
    // row headers must have scope="row"
    const rowThs = wrapper.findAll('tbody th[scope="row"]');
    expect(rowThs.length).toBe(2);
  });

  it('applies highlightRow class when highlightRow prop matches a row name', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX, highlightRow: '043_NSOP' },
    });
    const rows = wrapper.findAll('tbody tr');
    expect(rows[0].classes()).toContain('frm-row-highlight');
    expect(rows[1].classes()).not.toContain('frm-row-highlight');
  });

  it('does not apply highlightRow class when highlightRow is null', () => {
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: SAMPLE_MATRIX, highlightRow: null },
    });
    const rows = wrapper.findAll('tbody tr');
    for (const row of rows) {
      expect(row.classes()).not.toContain('frm-row-highlight');
    }
  });

  it('renders "—" for zero-value cells in 占比 mode', () => {
    const zeroMatrix = {
      rows: [{ name: 'R1', total: 100 }],
      cols: [{ name: 'C1', total: 0 }],
      cells: [[0]],
      row_pct: [[0]],
    };
    const wrapper = mount(ForwardReasonMatrix, {
      props: { matrix: zeroMatrix },
    });
    const tableText = wrapper.find('[data-testid="matrix-table"]').text();
    expect(tableText).toContain('—');
  });
});
