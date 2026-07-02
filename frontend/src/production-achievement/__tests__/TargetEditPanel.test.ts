// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import TargetEditPanel from '../components/TargetEditPanel.vue';

const ROWS = [
  { shift_code: 'D', workcenter_group: 'A1', target_qty: 100, updated_at: '2026-01-01', updated_by: 'alice' },
];

// DataTableColumn registers itself with the parent DataTable via an
// onMounted provide/inject hook, so columns/cells only appear in the DOM
// after the child-mount microtask queue flushes — mirrors the pattern
// already used by DataTable consumers elsewhere in this codebase.
async function mountAndFlush(props: Record<string, unknown>) {
  const wrapper = mount(TargetEditPanel, { props });
  await flushPromises();
  await wrapper.vm.$nextTick();
  return wrapper;
}

describe('TargetEditPanel', () => {
  it('shows the read-only note and hides edit controls when editForbidden is true', async () => {
    const wrapper = await mountAndFlush({ targets: ROWS, editForbidden: true });
    expect(wrapper.find('[data-testid="pa-target-readonly-note"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-target-edit-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pa-target-new-btn"]').exists()).toBe(false);
  });

  it('shows the edit button per row when not forbidden', async () => {
    const wrapper = await mountAndFlush({ targets: ROWS, editForbidden: false });
    expect(wrapper.find('[data-testid="pa-target-edit-btn"]').exists()).toBe(true);
  });

  it('rejects a negative target_qty client-side and does not emit save', async () => {
    const wrapper = await mountAndFlush({ targets: ROWS, editForbidden: false });
    await wrapper.find('[data-testid="pa-target-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    const input = wrapper.find('[data-testid="pa-target-edit-input"]');
    await input.setValue('-5');
    await input.trigger('keydown.enter');
    expect(wrapper.emitted('save')).toBeUndefined();
  });

  it('rejects non-numeric target_qty client-side and does not emit save', async () => {
    const wrapper = await mountAndFlush({ targets: ROWS, editForbidden: false });
    await wrapper.find('[data-testid="pa-target-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    const input = wrapper.find('[data-testid="pa-target-edit-input"]');
    await input.setValue('abc');
    await input.trigger('keydown.enter');
    expect(wrapper.emitted('save')).toBeUndefined();
  });

  it('emits save with the parsed integer for a valid edit', async () => {
    const wrapper = await mountAndFlush({ targets: ROWS, editForbidden: false });
    await wrapper.find('[data-testid="pa-target-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    const input = wrapper.find('[data-testid="pa-target-edit-input"]');
    await input.setValue('250');
    await input.trigger('keydown.enter');
    expect(wrapper.emitted('save')).toEqual([[{ shift_code: 'D', workcenter_group: 'A1', target_qty: 250 }]]);
  });

  it('renders empty-note when there are no targets', async () => {
    const wrapper = await mountAndFlush({ targets: [] });
    expect(wrapper.text()).toContain('尚未設定任何目標值');
  });
});
