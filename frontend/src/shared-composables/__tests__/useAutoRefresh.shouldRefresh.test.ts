// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { defineComponent, h } from 'vue';
import { mount } from '@vue/test-utils';

import { useAutoRefresh } from '../useAutoRefresh';

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

describe('useAutoRefresh shouldRefresh gate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(Math, 'random').mockReturnValue(0.5); // → zero jitter
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('skips onRefresh on a scheduled tick when shouldRefresh resolves false', async () => {
    const onRefresh = vi.fn();
    const shouldRefresh = vi.fn().mockResolvedValue(false);
    const { wrapper, api } = mountWith({ onRefresh, shouldRefresh, intervalMs: 1000, autoStart: false });

    api.startAutoRefresh();
    await vi.advanceTimersByTimeAsync(1000);

    expect(shouldRefresh).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();

    wrapper.unmount();
  });

  it('calls onRefresh on a scheduled tick when shouldRefresh resolves true', async () => {
    const onRefresh = vi.fn();
    const shouldRefresh = vi.fn().mockResolvedValue(true);
    const { wrapper, api } = mountWith({ onRefresh, shouldRefresh, intervalMs: 1000, autoStart: false });

    api.startAutoRefresh();
    await vi.advanceTimersByTimeAsync(1000);

    expect(onRefresh).toHaveBeenCalledTimes(1);

    wrapper.unmount();
  });

  it('gates triggerRefresh (visibility-regain path) the same as a scheduled tick', async () => {
    const onRefresh = vi.fn();
    const shouldRefresh = vi.fn().mockResolvedValue(false);
    const { wrapper, api } = mountWith({ onRefresh, shouldRefresh, intervalMs: 1000, autoStart: false });

    await api.triggerRefresh({ force: true });

    expect(shouldRefresh).toHaveBeenCalledTimes(1);
    expect(onRefresh).not.toHaveBeenCalled();

    wrapper.unmount();
  });

  it('omitting shouldRefresh preserves unconditional refresh-on-tick (backward compatible)', async () => {
    const onRefresh = vi.fn();
    const { wrapper, api } = mountWith({ onRefresh, intervalMs: 1000, autoStart: false });

    api.startAutoRefresh();
    await vi.advanceTimersByTimeAsync(1000);

    expect(onRefresh).toHaveBeenCalledTimes(1);

    wrapper.unmount();
  });
});
