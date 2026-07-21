import { describe, it, expect, vi } from 'vitest';

import { createFreshnessGate } from '../useFreshnessGate';

describe('createFreshnessGate', () => {
  it('does not refresh on the first check after construction (no markFresh call)', async () => {
    const fetchToken = vi.fn().mockResolvedValue('2026-07-21T10:00:00Z');
    const gate = createFreshnessGate(fetchToken);

    expect(await gate.shouldRefresh()).toBe(false);
  });

  it('refreshes once the polled token diverges from the seeded baseline', async () => {
    const fetchToken = vi.fn().mockResolvedValue('2026-07-21T10:00:00Z');
    const gate = createFreshnessGate(fetchToken);
    gate.markFresh('2026-07-21T09:00:00Z');

    expect(await gate.shouldRefresh()).toBe(true);
  });

  it('does not refresh again once the new token becomes the baseline', async () => {
    const fetchToken = vi.fn().mockResolvedValue('2026-07-21T10:00:00Z');
    const gate = createFreshnessGate(fetchToken);
    gate.markFresh('2026-07-21T09:00:00Z');

    expect(await gate.shouldRefresh()).toBe(true);
    expect(await gate.shouldRefresh()).toBe(false);
  });

  it('treats a null/undefined token as unknown and never signals refresh', async () => {
    const fetchToken = vi.fn().mockResolvedValue(null);
    const gate = createFreshnessGate(fetchToken);
    gate.markFresh('2026-07-21T09:00:00Z');

    expect(await gate.shouldRefresh()).toBe(false);
  });

  it('markFresh ignores a null/undefined token (keeps prior baseline)', async () => {
    const fetchToken = vi.fn().mockResolvedValue('2026-07-21T09:00:00Z');
    const gate = createFreshnessGate(fetchToken);
    gate.markFresh('2026-07-21T09:00:00Z');
    gate.markFresh(null);

    expect(await gate.shouldRefresh()).toBe(false);
  });

  it('seed() calls fetchToken and adopts its result as the baseline', async () => {
    const fetchToken = vi.fn()
      .mockResolvedValueOnce('2026-07-21T09:00:00Z')
      .mockResolvedValueOnce('2026-07-21T09:00:00Z')
      .mockResolvedValueOnce('2026-07-21T10:00:00Z');
    const gate = createFreshnessGate(fetchToken);

    await gate.seed();
    expect(await gate.shouldRefresh()).toBe(false); // unchanged since seed()
    expect(await gate.shouldRefresh()).toBe(true); // now diverges

    expect(fetchToken).toHaveBeenCalledTimes(3);
  });
});
