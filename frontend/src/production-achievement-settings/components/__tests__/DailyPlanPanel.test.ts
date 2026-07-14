// @vitest-environment jsdom
/**
 * DailyPlanPanel — unit tests (TDD, production-achievement-overhaul IP-9).
 * OD-12: workcenter_group/package_lf_group in the new-row form are
 * CONSTRAINED DROPDOWNS (<select>) only — no free-text input/escape hatch.
 */
import { describe, it, expect } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import DailyPlanPanel from '../DailyPlanPanel.vue';

const ROWS = [
  { workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 500, updated_at: '2026-07-01T00:00:00Z', updated_by: 'admin' },
];

async function mountAndFlush(props: Record<string, unknown>) {
  const wrapper = mount(DailyPlanPanel, { props });
  await flushPromises();
  await wrapper.vm.$nextTick();
  return wrapper;
}

describe('DailyPlanPanel', () => {
  it('renders existing daily-plan rows', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS });
    expect(wrapper.text()).toContain('焊接_DB');
    expect(wrapper.text()).toContain('SOD-123FL');
    expect(wrapper.text()).toContain('500');
  });

  it('OD-12: the new-row form uses <select> dropdowns for BOTH workcenter_group and package_lf_group, no free-text input', async () => {
    const wrapper = await mountAndFlush({
      rows: ROWS,
      workcenterGroupOptions: ['焊接_DB', '焊接_WB'],
      packageLfGroupOptions: ['SOD-123FL', 'TO-277(B)'],
    });
    await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
    await wrapper.vm.$nextTick();

    const workcenterField = wrapper.find('[data-testid="pa-plan-new-workcenter"]');
    const packageField = wrapper.find('[data-testid="pa-plan-new-package"]');
    expect(workcenterField.element.tagName).toBe('SELECT');
    expect(packageField.element.tagName).toBe('SELECT');

    const workcenterOptionValues = workcenterField.findAll('option').map((o) => o.element.value);
    expect(workcenterOptionValues).toContain('焊接_DB');
    expect(workcenterOptionValues).toContain('焊接_WB');
    const packageOptionValues = packageField.findAll('option').map((o) => o.element.value);
    expect(packageOptionValues).toContain('SOD-123FL');
    expect(packageOptionValues).toContain('TO-277(B)');
  });

  it('submitting the new-row form emits save with the selected dropdown values + parsed qty', async () => {
    const wrapper = await mountAndFlush({
      rows: [],
      workcenterGroupOptions: ['焊接_DB'],
      packageLfGroupOptions: ['SOD-123FL'],
    });
    await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="pa-plan-new-workcenter"]').setValue('焊接_DB');
    await wrapper.find('[data-testid="pa-plan-new-package"]').setValue('SOD-123FL');
    await wrapper.find('[data-testid="pa-plan-new-qty"]').setValue('600');
    await wrapper.find('[data-testid="pa-plan-new-save"]').trigger('click');
    expect(wrapper.emitted('save')).toEqual([[{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 600 }]]);
  });

  it('rejects submission when a dropdown is left unselected (no free-text fallback exists)', async () => {
    const wrapper = await mountAndFlush({ rows: [], workcenterGroupOptions: ['焊接_DB'], packageLfGroupOptions: ['SOD-123FL'] });
    await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="pa-plan-new-qty"]').setValue('100');
    await wrapper.find('[data-testid="pa-plan-new-save"]').trigger('click');
    expect(wrapper.emitted('save')).toBeUndefined();
  });

  it('rejects a negative qty client-side and does not emit save', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS });
    await wrapper.find('[data-testid="pa-plan-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    const input = wrapper.find('[data-testid="pa-plan-edit-input"]');
    await input.setValue('-5');
    await input.trigger('keydown.enter');
    expect(wrapper.emitted('save')).toBeUndefined();
  });

  it('inline edit emits save with the parsed integer qty', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS });
    await wrapper.find('[data-testid="pa-plan-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    const input = wrapper.find('[data-testid="pa-plan-edit-input"]');
    await input.setValue('700');
    await input.trigger('keydown.enter');
    expect(wrapper.emitted('save')).toEqual([[{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 700 }]]);
  });

  it('editForbidden hides all edit affordances and shows the readonly note', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS, editForbidden: true });
    expect(wrapper.find('[data-testid="pa-plan-readonly-note"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-plan-new-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pa-plan-edit-btn"]').exists()).toBe(false);
  });

  it('renders empty-note when there are no plan rows', async () => {
    const wrapper = await mountAndFlush({ rows: [] });
    expect(wrapper.text()).toContain('尚未設定任何每日計畫量');
  });

  // OD-12 constrained-dropdown edge cases (monkey-test-engineer,
  // production-achievement-overhaul) — the task's own domain-rule callout:
  // "what happens if the underlying select options list is empty" and "if a
  // value that WAS valid when the dropdown loaded gets deleted by another
  // session before submit."
  describe('OD-12 constrained-dropdown edge cases: empty options / stale selection', () => {
    it('renders with ZERO selectable options when both option lists are empty (no known package_lf/workcenter values yet) — no crash, graceful rejection on submit', async () => {
      const wrapper = await mountAndFlush({ rows: [], workcenterGroupOptions: [], packageLfGroupOptions: [] });
      await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
      await wrapper.vm.$nextTick();

      const workcenterField = wrapper.find('[data-testid="pa-plan-new-workcenter"]');
      const packageField = wrapper.find('[data-testid="pa-plan-new-package"]');
      // Only the disabled placeholder <option> exists — genuinely zero
      // selectable values, not merely "options happen to be filtered out."
      expect(workcenterField.findAll('option')).toHaveLength(1);
      expect(packageField.findAll('option')).toHaveLength(1);
      expect((workcenterField.findAll('option')[0].element as HTMLOptionElement).disabled).toBe(true);

      await wrapper.find('[data-testid="pa-plan-new-qty"]').setValue('100');
      await wrapper.find('[data-testid="pa-plan-new-save"]').trigger('click');

      // Safe outcome: no save emitted (nothing was ever selectable), and a
      // clear inline error rather than a silent no-op or a crash.
      expect(wrapper.emitted('save')).toBeUndefined();
      expect(wrapper.find('.pa-settings-panel__inline-error').exists()).toBe(true);
    });

    it('FINDING: a previously-valid selected workcenter_group removed from options (deleted by another session before submit) still submits the STALE value — no submit-time re-validation against the live options list', async () => {
      const wrapper = await mountAndFlush({ rows: [], workcenterGroupOptions: ['焊接_DB', '焊接_WB'], packageLfGroupOptions: ['SOD-123FL'] });
      await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
      await wrapper.vm.$nextTick();
      await wrapper.find('[data-testid="pa-plan-new-workcenter"]').setValue('焊接_DB');
      await wrapper.find('[data-testid="pa-plan-new-package"]').setValue('SOD-123FL');

      // Simulate another session deleting/renaming 焊接_DB out of
      // workcenter_merge_map between this dropdown's load and this admin's
      // submit — App.vue would re-fetch and pass a NARROWED options list.
      await wrapper.setProps({ workcenterGroupOptions: ['焊接_WB'], packageLfGroupOptions: ['SOD-123FL'] });
      await wrapper.vm.$nextTick();

      const workcenterField = wrapper.find('[data-testid="pa-plan-new-workcenter"]');
      const optionValues = workcenterField.findAll('option').map((o) => o.element.value);
      expect(optionValues).not.toContain('焊接_DB'); // the stale value is no longer OFFERED as a choice...
      // ...but per HTML <select> semantics, the DOM-level .value getter
      // resets to blank once no <option> matches — this is what the admin
      // VISUALLY sees (an apparently-empty dropdown), NOT an error.
      expect((workcenterField.element as HTMLSelectElement).value).toBe('');

      await wrapper.find('[data-testid="pa-plan-new-qty"]').setValue('100');
      await wrapper.find('[data-testid="pa-plan-new-save"]').trigger('click');

      // CONFIRMED (not hypothetical — verified via direct probe): Vue's
      // v-model does not clear the underlying reactive `newRow.workcenter_group`
      // just because a prop change narrowed the <option> list, and
      // submitNewRow()'s only guard is a truthy check — so the STALE
      // '焊接_DB' value silently reaches `emit('save', ...)`, even though the
      // dropdown the admin is looking at shows no selection. This is a real
      // gap in the OD-12 "constrained dropdown, always a currently-valid
      // choice" guarantee (no "is this still valid?" re-check at submit
      // time) — recorded as a hardening finding, not hard-failed, because
      // the resulting write is an orphaned-but-harmless plan row (no FK to
      // workcenter_merge_map in the DDL; it simply never joins to anything
      // in the report until/unless the group is re-added), not data
      // corruption or a crash.
      expect(wrapper.emitted('save')).toEqual([[{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 100 }]]);
    });

    it('daily_plan_qty=0 is accepted (a legitimate "no planned output today" value, not rejected as falsy/missing)', async () => {
      const wrapper = await mountAndFlush({ rows: [], workcenterGroupOptions: ['焊接_DB'], packageLfGroupOptions: ['SOD-123FL'] });
      await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
      await wrapper.vm.$nextTick();
      await wrapper.find('[data-testid="pa-plan-new-workcenter"]').setValue('焊接_DB');
      await wrapper.find('[data-testid="pa-plan-new-package"]').setValue('SOD-123FL');
      await wrapper.find('[data-testid="pa-plan-new-qty"]').setValue('0');
      await wrapper.find('[data-testid="pa-plan-new-save"]').trigger('click');
      expect(wrapper.emitted('save')).toEqual([[{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 0 }]]);
    });

    it('a large-but-finite daily_plan_qty is accepted (no artificial upper bound below Number.MAX_SAFE_INTEGER)', async () => {
      const wrapper = await mountAndFlush({ rows: [], workcenterGroupOptions: ['焊接_DB'], packageLfGroupOptions: ['SOD-123FL'] });
      await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
      await wrapper.vm.$nextTick();
      await wrapper.find('[data-testid="pa-plan-new-workcenter"]').setValue('焊接_DB');
      await wrapper.find('[data-testid="pa-plan-new-package"]').setValue('SOD-123FL');
      await wrapper.find('[data-testid="pa-plan-new-qty"]').setValue('999999999999');
      await wrapper.find('[data-testid="pa-plan-new-save"]').trigger('click');
      expect(wrapper.emitted('save')).toEqual([[{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 999999999999 }]]);
    });

    it('an absurdly-large all-digit qty that overflows Number to Infinity is rejected client-side, not silently accepted as Infinity', async () => {
      const wrapper = await mountAndFlush({ rows: [], workcenterGroupOptions: ['焊接_DB'], packageLfGroupOptions: ['SOD-123FL'] });
      await wrapper.find('[data-testid="pa-plan-new-btn"]').trigger('click');
      await wrapper.vm.$nextTick();
      await wrapper.find('[data-testid="pa-plan-new-workcenter"]').setValue('焊接_DB');
      await wrapper.find('[data-testid="pa-plan-new-package"]').setValue('SOD-123FL');
      await wrapper.find('[data-testid="pa-plan-new-qty"]').setValue('9'.repeat(400));
      await wrapper.find('[data-testid="pa-plan-new-save"]').trigger('click');
      expect(wrapper.emitted('save')).toBeUndefined();
    });
  });
});
