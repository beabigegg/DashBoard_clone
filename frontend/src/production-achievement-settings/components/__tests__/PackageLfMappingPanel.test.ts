// @vitest-environment jsdom
/**
 * PackageLfMappingPanel — unit tests (TDD, production-achievement-overhaul
 * IP-9). Renders exception rows + the known-unmapped hint list; inline
 * edit/delete/add-from-hint emit the correct payloads; fail-closed
 * editForbidden hides all edit affordances (mirrors TargetEditPanel.vue).
 */
import { describe, it, expect } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import PackageLfMappingPanel from '../PackageLfMappingPanel.vue';

const ROWS = [
  { raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL', updated_at: '2026-07-01T00:00:00Z', updated_by: 'admin' },
];

async function mountAndFlush(props: Record<string, unknown>) {
  const wrapper = mount(PackageLfMappingPanel, { props });
  await flushPromises();
  await wrapper.vm.$nextTick();
  return wrapper;
}

describe('PackageLfMappingPanel', () => {
  it('renders existing exception rows', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS });
    expect(wrapper.text()).toContain('SOD-123FL OP1');
    expect(wrapper.text()).toContain('SOD-123FL');
  });

  it('renders the known-unmapped hint list', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS, unmappedHints: ['NEW-RAW-VALUE'] });
    const hint = wrapper.find('[data-testid="pa-pkg-hint-item"]');
    expect(hint.exists()).toBe(true);
    expect(hint.text()).toContain('NEW-RAW-VALUE');
  });

  it('clicking a hint pre-fills the new-row form raw value', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS, unmappedHints: ['NEW-RAW-VALUE'] });
    await wrapper.find('[data-testid="pa-pkg-hint-item"]').trigger('click');
    await wrapper.vm.$nextTick();
    const rawInput = wrapper.find('[data-testid="pa-pkg-new-raw"]');
    expect((rawInput.element as HTMLInputElement).value).toBe('NEW-RAW-VALUE');
  });

  it('submitting the new-row form emits save with both fields', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS });
    await wrapper.find('[data-testid="pa-pkg-new-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="pa-pkg-new-raw"]').setValue('ANOTHER-RAW');
    await wrapper.find('[data-testid="pa-pkg-new-merged"]').setValue('ANOTHER-MERGED');
    await wrapper.find('[data-testid="pa-pkg-new-save"]').trigger('click');
    expect(wrapper.emitted('save')).toEqual([[{ raw_package_lf: 'ANOTHER-RAW', merged_group: 'ANOTHER-MERGED' }]]);
  });

  it('inline edit emits save with the updated merged_group', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS, editForbidden: false });
    await wrapper.find('[data-testid="pa-pkg-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    const input = wrapper.find('[data-testid="pa-pkg-edit-input"]');
    await input.setValue('SOD-123FL-RENAMED');
    await input.trigger('keydown.enter');
    expect(wrapper.emitted('save')).toEqual([[{ raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL-RENAMED' }]]);
  });

  it('delete button emits delete with the raw value', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS, editForbidden: false });
    await wrapper.find('[data-testid="pa-pkg-delete-btn"]').trigger('click');
    expect(wrapper.emitted('delete')).toEqual([['SOD-123FL OP1']]);
  });

  it('editForbidden hides ALL edit affordances and shows the readonly note (fail-closed, mirrors TargetEditPanel)', async () => {
    const wrapper = await mountAndFlush({ rows: ROWS, unmappedHints: ['X'], editForbidden: true });
    expect(wrapper.find('[data-testid="pa-pkg-readonly-note"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-pkg-new-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pa-pkg-edit-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pa-pkg-delete-btn"]').exists()).toBe(false);
    // Hint chips render (still informative) but are disabled, not actionable.
    const hintChip = wrapper.find('[data-testid="pa-pkg-hint-item"]');
    expect((hintChip.element as HTMLButtonElement).disabled).toBe(true);
  });

  it('renders empty-note when there are no exception rows', async () => {
    const wrapper = await mountAndFlush({ rows: [] });
    expect(wrapper.text()).toContain('尚未設定任何合併規則');
  });

  // Adversarial free-text input (monkey-test-engineer, production-achievement
  // -overhaul). Neither this panel's own submitNewRow()/confirmEdit() (only a
  // .trim()-non-empty check) nor the backend upsert_package_lf() route (only
  // a truthy check) restricts raw_package_lf/merged_group content — these are
  // genuinely free-text fields reachable by any whitelisted admin. Per the
  // Preventive Monkey Spec (Unicode/special chars, SQL-like/script-like
  // strings), assert the value passes through as INERT DATA end-to-end: sent
  // verbatim in the emitted payload, and rendered back as literal text (Vue's
  // default interpolation), never executed/interpreted.
  describe('adversarial free-text input (Unicode / emoji / SQL-like / script-like strings)', () => {
    const adversarialStrings = [
      { name: 'SQL-like injection string', value: "SOD'); DROP TABLE production_achievement_package_lf_map; --" },
      { name: 'script-like injection string', value: '<script>window.__pa_pkg_xss=1</script>' },
      { name: 'emoji + Unicode RTL override + Zero-Width Joiner', value: '\u5305\u88dd\ud83d\udce6\u200d\u202eevil' },
      { name: 'surrogate pair (emoji requiring 2 UTF-16 code units)', value: '𝔘𝔫𝔦𝔠𝔬𝔡𝔢-😀' },
    ];

    for (const adversarial of adversarialStrings) {
      it(`new-row submit passes "${adversarial.name}" through verbatim in both fields`, async () => {
        const wrapper = await mountAndFlush({ rows: ROWS });
        await wrapper.find('[data-testid="pa-pkg-new-btn"]').trigger('click');
        await wrapper.vm.$nextTick();
        await wrapper.find('[data-testid="pa-pkg-new-raw"]').setValue(adversarial.value);
        await wrapper.find('[data-testid="pa-pkg-new-merged"]').setValue(adversarial.value);
        await wrapper.find('[data-testid="pa-pkg-new-save"]').trigger('click');
        expect(wrapper.emitted('save')).toEqual([[{ raw_package_lf: adversarial.value, merged_group: adversarial.value }]]);
      });
    }

    it('a BOM-prefixed value has the BOM stripped by .trim() before submit (ECMAScript WhiteSpace semantics, not verbatim pass-through)', async () => {
      // Finding: unlike the other adversarial strings above, U+FEFF (BOM) is
      // spec'd as ECMAScript WhiteSpace, so submitNewRow()'s `.trim()` call
      // silently strips a leading/trailing BOM. This is DESIRABLE (prevents
      // an invisible-BOM-corrupted key that would silently fail to match its
      // own raw PACKAGE_LF at report-render time) — asserting the verified
      // real behavior here, not assuming naive verbatim pass-through.
      const wrapper = await mountAndFlush({ rows: ROWS });
      await wrapper.find('[data-testid="pa-pkg-new-btn"]').trigger('click');
      await wrapper.vm.$nextTick();
      await wrapper.find('[data-testid="pa-pkg-new-raw"]').setValue('﻿RAW VALUE');
      await wrapper.find('[data-testid="pa-pkg-new-merged"]').setValue('﻿RAW VALUE');
      await wrapper.find('[data-testid="pa-pkg-new-save"]').trigger('click');
      expect(wrapper.emitted('save')).toEqual([[{ raw_package_lf: 'RAW VALUE', merged_group: 'RAW VALUE' }]]);
    });

    it('a script-like merged_group value re-rendered from rows is shown as literal text, never executed', async () => {
      const maliciousRows = [{ raw_package_lf: 'RAW-XSS', merged_group: '<script>window.__pa_pkg_xss=1</script>', updated_at: 't', updated_by: 'admin' }];
      const wrapper = await mountAndFlush({ rows: maliciousRows });
      // Rendered as inert text content (DataTable's default cell template) —
      // the literal tag text must be present in innerText, and must never
      // have actually executed as a real <script> element.
      expect(wrapper.text()).toContain('<script>window.__pa_pkg_xss=1</script>');
      expect(wrapper.find('script').exists()).toBe(false);
      expect((window as unknown as { __pa_pkg_xss?: boolean }).__pa_pkg_xss).toBeUndefined();
    });

    it('an overlong raw_package_lf value (far exceeding the MySQL VARCHAR(60) column) is still accepted client-side and forwarded verbatim (server is the only length boundary)', async () => {
      const overlong = 'X'.repeat(500);
      const wrapper = await mountAndFlush({ rows: ROWS });
      await wrapper.find('[data-testid="pa-pkg-new-btn"]').trigger('click');
      await wrapper.vm.$nextTick();
      await wrapper.find('[data-testid="pa-pkg-new-raw"]').setValue(overlong);
      await wrapper.find('[data-testid="pa-pkg-new-merged"]').setValue('SOME-GROUP');
      await wrapper.find('[data-testid="pa-pkg-new-save"]').trigger('click');
      expect(wrapper.emitted('save')).toEqual([[{ raw_package_lf: overlong, merged_group: 'SOME-GROUP' }]]);
    });
  });
});
