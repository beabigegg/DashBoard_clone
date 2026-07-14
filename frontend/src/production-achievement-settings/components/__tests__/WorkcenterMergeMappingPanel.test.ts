// @vitest-environment jsdom
/**
 * WorkcenterMergeMappingPanel — unit tests (TDD, production-achievement
 * -overhaul IP-9). OD-8: renders the FULL raw workcenter_group universe
 * (not just the ~12 currently-included rows) with an include/exclude toggle
 * per row; merged-name rename input only for included rows.
 */
import { describe, it, expect } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import WorkcenterMergeMappingPanel from '../WorkcenterMergeMappingPanel.vue';

const FULL_LIST = [
  { raw_workcenter_group: '焊接_DB', included: true, merged_workcenter_group: '焊接_DB', updated_at: '2026-07-01T00:00:00Z', updated_by: 'admin' },
  { raw_workcenter_group: '切割', included: false, merged_workcenter_group: null, updated_at: null, updated_by: null },
];

async function mountAndFlush(props: Record<string, unknown>) {
  const wrapper = mount(WorkcenterMergeMappingPanel, { props });
  await flushPromises();
  await wrapper.vm.$nextTick();
  return wrapper;
}

describe('WorkcenterMergeMappingPanel', () => {
  it('renders BOTH an included row and a currently-excluded row (OD-8 full raw universe)', async () => {
    const wrapper = await mountAndFlush({ fullList: FULL_LIST });
    expect(wrapper.text()).toContain('焊接_DB');
    expect(wrapper.text()).toContain('切割'); // excluded raw group, still enumerated
    const toggles = wrapper.findAll('[data-testid="pa-wc-toggle"]');
    expect(toggles).toHaveLength(2);
    expect(toggles[0].attributes('aria-pressed')).toBe('true');
    expect(toggles[1].attributes('aria-pressed')).toBe('false');
  });

  it('toggling an EXCLUDED row emits include with a 1:1 default merged name', async () => {
    const wrapper = await mountAndFlush({ fullList: FULL_LIST });
    const toggles = wrapper.findAll('[data-testid="pa-wc-toggle"]');
    await toggles[1].trigger('click'); // 切割 row (excluded)
    expect(wrapper.emitted('include')).toEqual([[{ raw_workcenter_group: '切割', merged_workcenter_group: '切割' }]]);
  });

  it('toggling an INCLUDED row emits exclude with just the raw value', async () => {
    const wrapper = await mountAndFlush({ fullList: FULL_LIST });
    const toggles = wrapper.findAll('[data-testid="pa-wc-toggle"]');
    await toggles[0].trigger('click'); // 焊接_DB row (included)
    expect(wrapper.emitted('exclude')).toEqual([['焊接_DB']]);
  });

  it('rename on an included row emits rename with the new merged name', async () => {
    const wrapper = await mountAndFlush({ fullList: FULL_LIST });
    await wrapper.find('[data-testid="pa-wc-rename-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    const input = wrapper.find('[data-testid="pa-wc-name-input"]');
    await input.setValue('焊接_DB_RENAMED');
    await input.trigger('keydown.enter');
    expect(wrapper.emitted('rename')).toEqual([[{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB_RENAMED' }]]);
  });

  it('an excluded row shows no rename control and its merged name renders as "—"', async () => {
    const wrapper = await mountAndFlush({ fullList: FULL_LIST });
    const renameButtons = wrapper.findAll('[data-testid="pa-wc-rename-btn"]');
    expect(renameButtons).toHaveLength(1); // only for the one included row
  });

  it('editForbidden disables every toggle and shows the readonly note', async () => {
    const wrapper = await mountAndFlush({ fullList: FULL_LIST, editForbidden: true });
    expect(wrapper.find('[data-testid="pa-wc-readonly-note"]').exists()).toBe(true);
    const toggles = wrapper.findAll('[data-testid="pa-wc-toggle"]');
    toggles.forEach((t) => expect((t.element as HTMLButtonElement).disabled).toBe(true));
    expect(wrapper.find('[data-testid="pa-wc-rename-btn"]').exists()).toBe(false);
  });

  // Adversarial free-text input (monkey-test-engineer, production-achievement
  // -overhaul). raw_workcenter_group itself is NOT free text here (sourced
  // from the enumerated known-workcenter-groups list, OD-8) — only the rename
  // field (merged_workcenter_group) accepts arbitrary admin-typed text, with
  // only a `.trim()`-non-empty check client-side and a truthy check server-
  // side. Per the Preventive Monkey Spec (Unicode/special chars, SQL-like/
  // script-like strings), confirm this reaches `rename` as inert DATA, never
  // executed, and confirm it is genuinely reachable only through an INCLUDED
  // row (D2's own semantics — this is not testing D1's opposite default).
  describe('adversarial free-text input on the merged-name rename field', () => {
    const adversarialStrings = [
      { name: 'SQL-like injection string', value: "焊接'); DROP TABLE production_achievement_workcenter_merge_map; --" },
      { name: 'script-like injection string', value: '<script>window.__pa_wc_xss=1</script>' },
      { name: 'emoji + surrogate pair', value: '站點😀合併' },
    ];

    for (const adversarial of adversarialStrings) {
      it(`rename accepts "${adversarial.name}" and emits it verbatim`, async () => {
        const wrapper = await mountAndFlush({ fullList: FULL_LIST });
        await wrapper.find('[data-testid="pa-wc-rename-btn"]').trigger('click');
        await wrapper.vm.$nextTick();
        const input = wrapper.find('[data-testid="pa-wc-name-input"]');
        await input.setValue(adversarial.value);
        await input.trigger('keydown.enter');
        expect(wrapper.emitted('rename')).toEqual([[{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: adversarial.value }]]);
      });
    }

    it('a script-like merged_workcenter_group re-rendered from fullList is shown as literal text, never executed', async () => {
      const maliciousList = [
        { raw_workcenter_group: '焊接_DB', included: true, merged_workcenter_group: '<script>window.__pa_wc_xss=1</script>', updated_at: 't', updated_by: 'admin' },
      ];
      const wrapper = await mountAndFlush({ fullList: maliciousList });
      expect(wrapper.text()).toContain('<script>window.__pa_wc_xss=1</script>');
      expect(wrapper.find('script').exists()).toBe(false);
      expect((window as unknown as { __pa_wc_xss?: boolean }).__pa_wc_xss).toBeUndefined();
    });
  });
});
