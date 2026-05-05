// @vitest-environment jsdom
/**
 * Tests for shared-composables/useAutoRefresh.js
 *
 * Covers:
 * - Session expiry (pagehide) stops the refresh cycle
 * - Visibility change (hidden → visible) pauses then resumes
 * - 100-cycle run with fake timers — no memory leak (intervals cleaned up)
 *
 * NOTE: useAutoRefresh uses onMounted/onBeforeUnmount hooks, so it must be
 * called inside a component setup context. We use @vue/test-utils mountedApp
 * helper via defineComponent.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { defineComponent, h } from 'vue';
import { mount } from '@vue/test-utils';
import { useAutoRefresh } from '../../src/shared-composables/useAutoRefresh.ts';

// Helper: mount a component that calls useAutoRefresh with given options,
// returning { wrapper, refreshSpy, ...returned composable }
function mountWithAutoRefresh(options = {}) {
  const refreshSpy = vi.fn().mockResolvedValue(undefined);
  let composable = null;

  const TestComponent = defineComponent({
    setup() {
      composable = useAutoRefresh({
        onRefresh: refreshSpy,
        intervalMs: 1000,
        autoStart: true,
        refreshOnVisible: true,
        ...options,
      });
      return () => h('div');
    },
  });

  const wrapper = mount(TestComponent, { attachTo: document.body });
  return { wrapper, refreshSpy, composable: () => composable };
}

describe('useAutoRefresh — visibility change', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not call onRefresh when document is hidden', async () => {
    const { wrapper, refreshSpy } = mountWithAutoRefresh({ intervalMs: 500 });

    // Simulate hidden tab
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });

    // Advance past multiple intervals
    await vi.advanceTimersByTimeAsync(2000);

    // onRefresh should not have been called while hidden
    expect(refreshSpy).not.toHaveBeenCalled();

    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    wrapper.unmount();
  });

  it('triggers immediate refresh when tab becomes visible', async () => {
    const { wrapper, refreshSpy } = mountWithAutoRefresh({ intervalMs: 600000 }); // Very long interval

    // Document starts visible
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });

    // Go hidden: no immediate refresh
    Object.defineProperty(document, 'hidden', { value: true, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));

    // Nothing should have been called
    expect(refreshSpy).not.toHaveBeenCalled();

    // Now become visible — should trigger immediate refresh (force=true, resetTimer=true)
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));

    // Give the microtask queue a chance to process (triggerRefresh is async)
    await Promise.resolve();
    await Promise.resolve();

    // Should trigger one immediate refresh
    expect(refreshSpy).toHaveBeenCalledTimes(1);

    wrapper.unmount();
  });

  it('pagehide stops the refresh timer', async () => {
    const { wrapper, refreshSpy } = mountWithAutoRefresh({ intervalMs: 300 });

    Object.defineProperty(document, 'hidden', { value: false, configurable: true });

    // Fire pagehide to simulate page being hidden/frozen
    window.dispatchEvent(new Event('pagehide'));

    await vi.advanceTimersByTimeAsync(2000);

    // After pagehide the timer should have been stopped
    expect(refreshSpy).not.toHaveBeenCalled();

    wrapper.unmount();
  });
});

describe('useAutoRefresh — timer cleanup (100-cycle)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('completes 100 cycles without stacking timers (no memory leak)', async () => {
    const onRefresh = vi.fn();

    let composable = null;
    const TestComponent = defineComponent({
      setup() {
        composable = useAutoRefresh({
          onRefresh,
          // Use a large interval so we control each tick precisely
          intervalMs: 1000,
          autoStart: true,
          refreshOnVisible: true,
        });
        return () => h('div');
      },
    });

    Object.defineProperty(document, 'hidden', { value: false, configurable: true });

    const wrapper = mount(TestComponent, { attachTo: document.body });

    // Advance 100 timer cycles. With jitter at ±15% of 1000ms,
    // each interval is between 850–1150ms. Advancing 1200ms per tick
    // ensures each timer fires exactly once.
    for (let i = 0; i < 100; i++) {
      await vi.advanceTimersByTimeAsync(1200);
    }

    // Should have gotten approximately 100 calls
    expect(onRefresh.mock.calls.length).toBeGreaterThanOrEqual(95);

    // Unmount and verify no further calls
    wrapper.unmount();
    const callsAtUnmount = onRefresh.mock.calls.length;

    await vi.advanceTimersByTimeAsync(5000);

    // After unmount, no new calls should occur
    expect(onRefresh.mock.calls.length).toBe(callsAtUnmount);
  });
});

describe('useAutoRefresh — unmount cleanup', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stopAutoRefresh halts the timer', async () => {
    let composableRef = null;
    const onRefresh = vi.fn();

    const TestComponent = defineComponent({
      setup() {
        composableRef = useAutoRefresh({ onRefresh, intervalMs: 200, autoStart: true });
        return () => h('div');
      },
    });

    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    const wrapper = mount(TestComponent, { attachTo: document.body });

    // Manually stop
    composableRef.stopAutoRefresh();

    await vi.advanceTimersByTimeAsync(1000);

    expect(onRefresh).not.toHaveBeenCalled();

    wrapper.unmount();
  });

  it('createAbortSignal aborts previous controller for same key', () => {
    let composableRef = null;

    const TestComponent = defineComponent({
      setup() {
        composableRef = useAutoRefresh({ onRefresh: vi.fn(), intervalMs: 1000, autoStart: false });
        return () => h('div');
      },
    });

    const wrapper = mount(TestComponent, { attachTo: document.body });

    const signal1 = composableRef.createAbortSignal('fetch');
    expect(signal1.aborted).toBe(false);

    // Second call with same key should abort the first
    const signal2 = composableRef.createAbortSignal('fetch');
    expect(signal1.aborted).toBe(true);
    expect(signal2.aborted).toBe(false);

    wrapper.unmount();
  });

  it('abortAllRequests cancels all tracked controllers on unmount', () => {
    let composableRef = null;

    const TestComponent = defineComponent({
      setup() {
        composableRef = useAutoRefresh({ onRefresh: vi.fn(), intervalMs: 1000, autoStart: false });
        return () => h('div');
      },
    });

    const wrapper = mount(TestComponent, { attachTo: document.body });

    const sig1 = composableRef.createAbortSignal('a');
    const sig2 = composableRef.createAbortSignal('b');

    wrapper.unmount();

    expect(sig1.aborted).toBe(true);
    expect(sig2.aborted).toBe(true);
  });
});
