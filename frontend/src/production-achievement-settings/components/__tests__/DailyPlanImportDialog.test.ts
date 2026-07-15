// @vitest-environment jsdom
/**
 * DailyPlanImportDialog — unit tests (business-rules.md PA-16).
 * Decision 6: invalid_* rows are never selectable (orphan-prevention).
 * Decision 8: "unchanged" rows are shown but NOT pre-selected.
 */
import { describe, it, expect } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import DailyPlanImportDialog from '../DailyPlanImportDialog.vue';
import type { DailyPlanImportPreview } from '../../composables/useProductionAchievementSettings';

const PREVIEW: DailyPlanImportPreview = {
  rows: [
    {
      workcenter_group: '成型', package_lf_group: 'NEW-PKG', daily_plan_qty: 100, current_qty: null,
      status: 'new', source_sheet: '成型', source_block: '成型', importable: true, default_selected: true, warning: null,
    },
    {
      workcenter_group: '成型', package_lf_group: 'UPDATED-PKG', daily_plan_qty: 200, current_qty: 150,
      status: 'update', source_sheet: '成型', source_block: '成型', importable: true, default_selected: true, warning: null,
    },
    {
      workcenter_group: '成型', package_lf_group: 'SAME-PKG', daily_plan_qty: 300, current_qty: 300,
      status: 'unchanged', source_sheet: '成型', source_block: '成型', importable: true, default_selected: false, warning: null,
    },
    {
      workcenter_group: '成型', package_lf_group: 'DFN2510/0603', daily_plan_qty: 50, current_qty: null,
      status: 'invalid_package', source_sheet: '成型', source_block: '成型', importable: false, default_selected: false,
      warning: 'Package「DFN2510/0603」無法對應到現有 package_lf_group，請先於 Package 對應設定建立合併對應',
    },
  ],
  missing_from_file: [
    { workcenter_group: '去膠', package_lf_group: 'OLD-PKG', daily_plan_qty: 999 },
  ],
  summary: { total_parsed: 4, new: 1, update: 1, unchanged: 1, invalid: 1, missing_from_file: 1 },
};

async function mountAndFlush(props: Record<string, unknown>) {
  const wrapper = mount(DailyPlanImportDialog, { props });
  await flushPromises();
  await wrapper.vm.$nextTick();
  return wrapper;
}

describe('DailyPlanImportDialog', () => {
  it('renders nothing when closed', async () => {
    const wrapper = await mountAndFlush({ open: false, preview: PREVIEW });
    expect(wrapper.find('[data-testid="pa-plan-import-dialog"]').exists()).toBe(false);
  });

  it('emits select-file when a file is chosen', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: null });
    const input = wrapper.find('[data-testid="pa-plan-import-file"]');
    const file = new File(['dummy'], 'report.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    Object.defineProperty(input.element, 'files', { value: [file] });
    await input.trigger('change');
    const emitted = wrapper.emitted('select-file');
    expect(emitted).toBeTruthy();
    expect((emitted as unknown[][])[0][0]).toBe(file);
  });

  it('shows the summary counts', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    const summary = wrapper.find('[data-testid="pa-plan-import-summary"]').text();
    expect(summary).toContain('4');
    expect(summary).toContain('新增 1');
    expect(summary).toContain('更新 1');
    expect(summary).toContain('未變更 1');
    expect(summary).toContain('無法匯入 1');
  });

  it('renders status tags for each row', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    const text = wrapper.text();
    expect(text).toContain('新增');
    expect(text).toContain('更新');
    expect(text).toContain('未變更');
    expect(text).toContain('無法匯入');
    expect(text).toContain('DFN2510/0603');
  });

  it('pre-selects new/update rows, leaves unchanged unchecked, disables invalid rows', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    const newCheckbox = wrapper.find('[data-testid="pa-plan-import-row-select-成型::NEW-PKG"]').element as HTMLInputElement;
    const updateCheckbox = wrapper.find('[data-testid="pa-plan-import-row-select-成型::UPDATED-PKG"]').element as HTMLInputElement;
    const unchangedCheckbox = wrapper.find('[data-testid="pa-plan-import-row-select-成型::SAME-PKG"]').element as HTMLInputElement;
    const invalidCheckbox = wrapper.find('[data-testid="pa-plan-import-row-select-成型::DFN2510/0603"]').element as HTMLInputElement;

    expect(newCheckbox.checked).toBe(true);
    expect(updateCheckbox.checked).toBe(true);
    expect(unchangedCheckbox.checked).toBe(false);
    expect(invalidCheckbox.checked).toBe(false);
    expect(invalidCheckbox.disabled).toBe(true);
  });

  it('clicking an invalid row checkbox does not select it (toggleRow no-ops on non-importable rows)', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    const invalidCheckbox = wrapper.find('[data-testid="pa-plan-import-row-select-成型::DFN2510/0603"]');
    await invalidCheckbox.trigger('change');
    await wrapper.find('[data-testid="pa-plan-import-confirm"]').trigger('click');
    const rows = (wrapper.emitted('confirm') as unknown[][])[0][0] as { package_lf_group: string }[];
    expect(rows.map((r) => r.package_lf_group)).not.toContain('DFN2510/0603');
  });

  it('confirm emits only the checked importable rows with clean {workcenter_group, package_lf_group, daily_plan_qty} shape', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    await wrapper.find('[data-testid="pa-plan-import-confirm"]').trigger('click');
    const rows = (wrapper.emitted('confirm') as unknown[][])[0][0] as Record<string, unknown>[];
    expect(rows).toEqual([
      { workcenter_group: '成型', package_lf_group: 'NEW-PKG', daily_plan_qty: 100 },
      { workcenter_group: '成型', package_lf_group: 'UPDATED-PKG', daily_plan_qty: 200 },
    ]);
  });

  it('unchecking a pre-selected row excludes it from the confirm payload', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    await wrapper.find('[data-testid="pa-plan-import-row-select-成型::UPDATED-PKG"]').trigger('change');
    await wrapper.find('[data-testid="pa-plan-import-confirm"]').trigger('click');
    const rows = (wrapper.emitted('confirm') as unknown[][])[0][0] as { package_lf_group: string }[];
    expect(rows.map((r) => r.package_lf_group)).toEqual(['NEW-PKG']);
  });

  it('confirm button is disabled when zero rows are selected', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    await wrapper.find('[data-testid="pa-plan-import-row-select-成型::NEW-PKG"]').trigger('change');
    await wrapper.find('[data-testid="pa-plan-import-row-select-成型::UPDATED-PKG"]').trigger('change');
    const confirmBtn = wrapper.find('[data-testid="pa-plan-import-confirm"]').element as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);
  });

  it('renders the "missing from file" notice', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW });
    const missing = wrapper.find('[data-testid="pa-plan-import-missing"]');
    expect(missing.exists()).toBe(true);
    expect(missing.text()).toContain('去膠');
    expect(missing.text()).toContain('OLD-PKG');
    expect(missing.text()).toContain('999');
  });

  it('shows the result summary after a successful confirm and hides the preview table', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW, confirmResult: { acknowledged: true, upserted: 2 } });
    expect(wrapper.find('[data-testid="pa-plan-import-result"]').text()).toContain('2');
    expect(wrapper.find('[data-testid="pa-plan-import-confirm"]').exists()).toBe(false);
  });

  it('clicking 關閉 after a result emits close', async () => {
    const wrapper = await mountAndFlush({ open: true, preview: PREVIEW, confirmResult: { acknowledged: true, upserted: 2 } });
    await wrapper.find('[data-testid="pa-plan-import-done"]').trigger('click');
    expect(wrapper.emitted('close')).toBeTruthy();
  });
});
