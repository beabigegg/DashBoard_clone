// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { defineComponent, h } from 'vue';
import { mount } from '@vue/test-utils';

import { useAutoRefresh } from '../useAutoRefresh';

// Mount inside a component so onMounted/onBeforeUnmount lifecycle hooks fire.
function mountWith(options: Record<string, unknown>) {
  let api: ReturnType<typeof useAutoRefresh> | null = null;
  const Comp = defineComponent({
    setup() {
      api = useAutoRefresh(options);
      return () => h('div');
    },
  });
  const wrapper = mount(Comp);
  return { wrapper, api: api as unknown as ReturnType<typeof useAutoRefresh> };
}

describe('useAutoRefresh dynamic interval (B-2)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // jitter uses Math.random; pin it so interval math is deterministic.
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // → zero jitter
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('re-reads a getter interval on each scheduling cycle', async () => {
    const onRefresh = vi.fn();
    let interval = 1000;
    const { wrapper, api } = mountWith({
      onRefresh,
      intervalMs: () => interval,
      autoStart: false,
    });

    api.startAutoRefresh();
    // Cycle 1 uses 1000ms (timer scheduled at start).
    await vi.advanceTimersByTimeAsync(1000);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    // Bump the interval. Cycle 2's timer was scheduled (with 1000) when cycle 1
    // fired, so it still fires at +1000; the getter re-read takes effect for the
    // timer scheduled when cycle 2 fires.
    interval = 4000;
    await vi.advanceTimersByTimeAsync(1000);
    expect(onRefresh).toHaveBeenCalledTimes(2); // cycle 2 fired; next timer = 4000ms

    // Within the new 4000ms window: no fire yet.
    await vi.advanceTimersByTimeAsync(1000);
    expect(onRefresh).toHaveBeenCalledTimes(2);

    // Complete the 4000ms window → cycle 3 fires (proves the getter was re-read).
    await vi.advanceTimersByTimeAsync(3000);
    expect(onRefresh).toHaveBeenCalledTimes(3);

    wrapper.unmount();
  });

  it('still accepts a fixed numeric interval (backward compatible)', async () => {
    const onRefresh = vi.fn();
    const { wrapper, api } = mountWith({
      onRefresh,
      intervalMs: 2000,
      autoStart: false,
    });

    api.startAutoRefresh();
    await vi.advanceTimersByTimeAsync(2000);
    expect(onRefresh).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2000);
    expect(onRefresh).toHaveBeenCalledTimes(2);

    wrapper.unmount();
  });
});
