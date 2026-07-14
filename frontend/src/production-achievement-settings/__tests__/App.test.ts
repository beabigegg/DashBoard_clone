// @vitest-environment jsdom
/**
 * production-achievement-settings/App.vue — smart-page wiring tests (TDD,
 * production-achievement-overhaul IP-9).
 *
 * Fetch/PUT/CSRF wiring per panel; editForbidden flips read-only on the
 * FIRST 403 from ANY panel (shared fail-closed state); OD-5 propagation
 * -delay note shown after a successful save; OD-6 no unsaved-edit navigation
 * guard (no beforeunload/route-leave listener is ever registered).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import App from '../App.vue';

const navigateMock = vi.fn();
vi.mock('../../core/shell-navigation', () => ({
  navigateToRuntimeRoute: (...args: unknown[]) => navigateMock(...args),
}));

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

function envelope(data: unknown) {
  return jsonResponse({ success: true, data, meta: {} });
}

const PKG_ROWS = [{ raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL', updated_at: 't', updated_by: 'admin' }];
const WC_ROWS = [{ raw_workcenter_group: '焊接_DB', merged_workcenter_group: '焊接_DB', updated_at: 't', updated_by: 'admin' }];
const PLAN_ROWS = [{ workcenter_group: '焊接_DB', package_lf_group: 'SOD-123FL', daily_plan_qty: 500, updated_at: 't', updated_by: 'admin' }];

function setupFetchMock(overrides: Record<string, () => Response> = {}) {
  const fetchMock = vi.fn((url: string, options?: RequestInit) => {
    const u = String(url);
    const method = (options?.method || 'GET').toUpperCase();
    const key = `${method} ${u.split('?')[0]}`;
    for (const [pattern, handler] of Object.entries(overrides)) {
      if (key.includes(pattern)) return Promise.resolve(handler());
    }
    if (u.includes('/api/production-achievement/package-lf-map')) return Promise.resolve(envelope(PKG_ROWS));
    if (u.includes('/api/production-achievement/known-package-lf-values')) return Promise.resolve(envelope({ package_lf_values: ['NEW-VAL'] }));
    if (u.includes('/api/production-achievement/workcenter-merge-map')) return Promise.resolve(envelope(WC_ROWS));
    if (u.includes('/api/production-achievement/known-workcenter-groups')) return Promise.resolve(envelope({ raw_workcenter_groups: ['焊接_DB', '切割'] }));
    if (u.includes('/api/production-achievement/daily-plans')) return Promise.resolve(envelope(PLAN_ROWS));
    return Promise.resolve(envelope(null));
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe('production-achievement-settings App.vue', () => {
  const originalFetch = global.fetch;
  const metaTag = document.createElement('meta');

  beforeEach(() => {
    metaTag.setAttribute('name', 'csrf-token');
    metaTag.setAttribute('content', 'test-csrf-token');
    document.head.appendChild(metaTag);
    navigateMock.mockClear();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    document.head.removeChild(metaTag);
    vi.restoreAllMocks();
  });

  it('fetches all 5 endpoints on mount and renders each panel with its data', async () => {
    setupFetchMock();
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    expect(wrapper.text()).toContain('SOD-123FL OP1');
    expect(wrapper.text()).toContain('焊接_DB');
    expect(wrapper.text()).toContain('500');
    // OD-8: the full raw universe includes 切割 (currently excluded), not just the included row.
    expect(wrapper.text()).toContain('切割');
    wrapper.unmount();
  });

  it('a package-lf-map save PUTs with the CSRF header and the JSON payload', async () => {
    const fetchMock = setupFetchMock();
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    await wrapper.find('[data-testid="pa-pkg-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').setValue('SOD-123FL-NEW');
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').trigger('keydown.enter');
    await flushPromises();

    const putCall = fetchMock.mock.calls.find(([, opts]) => (opts as RequestInit | undefined)?.method === 'PUT');
    expect(putCall).toBeDefined();
    const [url, options] = putCall!;
    expect(String(url)).toContain('/api/production-achievement/package-lf-map');
    expect((options as RequestInit).headers as Record<string, string>).toMatchObject({ 'X-CSRF-Token': 'test-csrf-token' });
    expect(JSON.parse((options as RequestInit).body as string)).toEqual({ raw_package_lf: 'SOD-123FL OP1', merged_group: 'SOD-123FL-NEW' });
    wrapper.unmount();
  });

  it('OD-5: shows the propagation-delay note after a successful save', async () => {
    setupFetchMock();
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-settings-save-note"]').exists()).toBe(false);

    await wrapper.find('[data-testid="pa-pkg-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').setValue('SOD-123FL-NEW');
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').trigger('keydown.enter');
    await flushPromises();

    const note = wrapper.find('[data-testid="pa-settings-save-note"]');
    expect(note.exists()).toBe(true);
    expect(note.text()).toContain('下次資料重新整理');

    await wrapper.find('[data-testid="pa-settings-save-note-dismiss"]').trigger('click');
    expect(wrapper.find('[data-testid="pa-settings-save-note"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('a 403 on ANY panel write flips editForbidden SHARED across all 3 panels (fail-closed)', async () => {
    setupFetchMock({
      'PUT /api/production-achievement/package-lf-map': () =>
        jsonResponse({ success: false, error: { code: 'FORBIDDEN', message: '無權限' }, meta: {} }, 403),
    });
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    await wrapper.find('[data-testid="pa-pkg-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').setValue('X');
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').trigger('keydown.enter');
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-pkg-readonly-note"]').exists()).toBe(true);
    // The SAME shared flag disables the OTHER two panels too — one language everywhere.
    expect(wrapper.find('[data-testid="pa-wc-readonly-note"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pa-plan-readonly-note"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it('a 503 write failure surfaces an error WITHOUT flipping editForbidden (OPS disabled, not a permission denial)', async () => {
    setupFetchMock({
      'PUT /api/production-achievement/package-lf-map': () =>
        jsonResponse({ success: false, error: { code: 'SERVICE_UNAVAILABLE', message: '服務暫停' }, meta: {} }, 503),
    });
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    await wrapper.find('[data-testid="pa-pkg-edit-btn"]').trigger('click');
    await wrapper.vm.$nextTick();
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').setValue('X');
    await wrapper.find('[data-testid="pa-pkg-edit-input"]').trigger('keydown.enter');
    await flushPromises();

    expect(wrapper.find('[data-testid="pa-pkg-readonly-note"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pa-pkg-edit-error"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it('OD-6: registers no beforeunload / route-leave guard for unsaved edits', async () => {
    setupFetchMock();
    const addSpy = vi.spyOn(window, 'addEventListener');
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    await wrapper.find('[data-testid="pa-pkg-edit-btn"]').trigger('click'); // open an "unsaved" edit
    await wrapper.vm.$nextTick();

    expect(addSpy.mock.calls.some(([type]) => type === 'beforeunload')).toBe(false);
    wrapper.unmount();
  });

  it('← 返回報表 navigates back to /production-achievement', async () => {
    setupFetchMock();
    const wrapper = mount(App, { attachTo: document.body });
    await flushPromises();

    await wrapper.find('[data-testid="pa-settings-back-btn"]').trigger('click');
    expect(navigateMock).toHaveBeenCalledWith('/production-achievement');
    wrapper.unmount();
  });

  // ── FINDING: concurrent-panel race on the shared `editSaving` flag ────────
  // monkey-test-engineer, production-achievement-overhaul. Task-specific
  // domain probe: "race conditions between two settings panels being edited
  // concurrently." useProductionAchievementSettings.ts's savePackageLf() /
  // saveWorkcenterMerge() / saveDailyPlan() all set the ONE SHARED
  // `editSaving` ref true/false around their own fetch, but NONE of them
  // checks `if (editSaving.value) return` first (unlike useProductionAchievement
  // .ts's runQuery(), which DOES guard with `if (loading.value) return`). The
  // per-row BUTTONS that open a NEW edit are gated by :disabled="editSaving",
  // but an inline-edit <input>'s own @keydown.enter handler is NOT gated —
  // only the buttons shown while NOT editing are. So two edits opened BEFORE
  // either save starts (an ordinary admin workflow: open edit on panel A, get
  // distracted, open edit on panel B) can both be submitted with editSaving
  // providing no real mutual exclusion between them.
  describe('FINDING: concurrent saves across two different panels race on the shared editSaving flag', () => {
    it('opening edits on PackageLfMappingPanel AND DailyPlanPanel BEFORE either submits, then submitting both in quick succession, fires BOTH PUT requests concurrently', async () => {
      let resolvePkgPut!: (v: Response) => void;
      const pkgPutPromise = new Promise<Response>((resolve) => {
        resolvePkgPut = resolve;
      });
      let dailyPlanPutCalled = false;

      setupFetchMock({
        // package-lf-map's PUT is deliberately SLOW (a deferred promise this
        // test resolves manually) so its in-flight window is observable.
        'PUT /api/production-achievement/package-lf-map': () => pkgPutPromise as unknown as Response,
      });
      const wrapper = mount(App, { attachTo: document.body });
      await flushPromises();

      // Open BOTH edits first, while editSaving is still false for both.
      await wrapper.find('[data-testid="pa-pkg-edit-btn"]').trigger('click');
      await wrapper.vm.$nextTick();
      await wrapper.find('[data-testid="pa-plan-edit-btn"]').trigger('click');
      await wrapper.vm.$nextTick();

      await wrapper.find('[data-testid="pa-pkg-edit-input"]').setValue('SOD-123FL-RACE');
      await wrapper.find('[data-testid="pa-plan-edit-input"]').setValue('999');

      // Submit PackageLfMappingPanel's edit first — its PUT will hang on the
      // deferred promise above (savePackageLf() sets editSaving=true, no
      // reentrancy guard exists to stop what happens next).
      await wrapper.find('[data-testid="pa-pkg-edit-input"]').trigger('keydown.enter');
      await wrapper.vm.$nextTick();
      // At this point the package-lf-map PUT is deliberately still pending
      // (the deferred promise above has not been resolved) — editSaving is
      // now true, and per the "one language everywhere" shared-flag design,
      // every panel's NOT-currently-editing buttons should be disabled.
      expect((wrapper.find('[data-testid="pa-plan-new-btn"]').element as HTMLButtonElement).disabled).toBe(true);

      // WITHOUT waiting for the first PUT to resolve, submit the
      // ALREADY-OPEN DailyPlanPanel edit too — its input's own keydown.enter
      // handler has no editSaving gate.
      const fetchMock = global.fetch as unknown as ReturnType<typeof vi.fn>;
      const callsBeforeSecondSubmit = fetchMock.mock.calls.length;
      await wrapper.find('[data-testid="pa-plan-edit-input"]').trigger('keydown.enter');
      await wrapper.vm.$nextTick();

      // CONFIRMS the finding: a second panel's PUT fires concurrently, while
      // the first panel's PUT is STILL unresolved — the shared editSaving
      // flag provided no mutual exclusion for an edit that was already open.
      const dailyPlanPutFired = fetchMock.mock.calls
        .slice(callsBeforeSecondSubmit)
        .some(([url, opts]) => String(url).includes('/api/production-achievement/daily-plans') && (opts as RequestInit)?.method === 'PUT');
      dailyPlanPutCalled = dailyPlanPutFired;
      expect(dailyPlanPutCalled).toBe(true);

      // Resolve the slow package-lf-map PUT now; the safe-outcome floor is
      // that everything settles cleanly afterwards (no crash, no
      // permanently-stuck editSaving=true) even though two writes overlapped.
      resolvePkgPut(jsonResponse({ success: true, data: null, meta: {} }));
      await flushPromises();

      expect(wrapper.find('[data-testid="pa-pkg-edit-input"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="pa-plan-edit-input"]').exists()).toBe(false);
      wrapper.unmount();
    });
  });
});
