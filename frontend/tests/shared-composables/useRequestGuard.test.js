/**
 * Tests for shared-composables/useRequestGuard.js
 *
 * Covers:
 * - Stale response is dropped (response arrives after a newer request started)
 * - Rapid pagination dedup: firing 5 quick requests, only last one is active
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useRequestGuard } from '../../src/shared-composables/useRequestGuard.ts';

describe('useRequestGuard — basic API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts with currentId 0, so isStaleRequest(0) returns false before any call', () => {
    const { isStaleRequest } = useRequestGuard();
    // currentId starts at 0; no calls to nextRequestId yet
    // isStaleRequest(0) checks 0 !== 0 → false (not stale)
    expect(isStaleRequest(0)).toBe(false);
  });

  it('nextRequestId increments monotonically', () => {
    const { nextRequestId } = useRequestGuard();
    expect(nextRequestId()).toBe(1);
    expect(nextRequestId()).toBe(2);
    expect(nextRequestId()).toBe(3);
  });

  it('isStaleRequest returns false for current request id', () => {
    const { nextRequestId, isStaleRequest } = useRequestGuard();
    const id = nextRequestId();
    expect(isStaleRequest(id)).toBe(false);
  });

  it('isStaleRequest returns true for old request id', () => {
    const { nextRequestId, isStaleRequest } = useRequestGuard();
    const oldId = nextRequestId(); // 1
    nextRequestId();               // 2 — now current
    expect(isStaleRequest(oldId)).toBe(true);
  });
});

describe('useRequestGuard — stale response drop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('drops stale response when newer request has started', async () => {
    const { nextRequestId, isStaleRequest } = useRequestGuard();
    const results = [];

    // Simulate: request #1 is issued, then request #2 starts before #1 resolves
    const reqId1 = nextRequestId();

    // Slow request #1 resolves after req #2 is started
    const slowRequest = new Promise((resolve) => setTimeout(() => resolve('result-1'), 50));

    // Request #2 starts immediately
    const reqId2 = nextRequestId();

    // Simulate resolving slow request
    const result1 = await slowRequest;
    if (!isStaleRequest(reqId1)) {
      results.push({ id: reqId1, data: result1 });
    }

    // Simulate fast request #2 response
    const result2 = 'result-2';
    if (!isStaleRequest(reqId2)) {
      results.push({ id: reqId2, data: result2 });
    }

    // Only request 2 result should be accepted
    expect(results).toHaveLength(1);
    expect(results[0].data).toBe('result-2');
    expect(results[0].id).toBe(reqId2);
  });

  it('accepts the last response when requests resolve out of order', async () => {
    const { nextRequestId, isStaleRequest } = useRequestGuard();
    const accepted = [];

    const id1 = nextRequestId();
    const id2 = nextRequestId();
    const id3 = nextRequestId();

    // Requests resolve in reverse order: 3, 2, 1
    [id3, id2, id1].forEach((id) => {
      if (!isStaleRequest(id)) {
        accepted.push(id);
      }
    });

    // Only id3 is current
    expect(accepted).toEqual([id3]);
  });
});

describe('useRequestGuard — rapid pagination dedup (5 quick requests)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('only the last of 5 rapid requests is considered active', () => {
    const { nextRequestId, isStaleRequest } = useRequestGuard();

    // Fire 5 requests quickly (simulating rapid page changes)
    const ids = [];
    for (let i = 0; i < 5; i++) {
      ids.push(nextRequestId());
    }

    const lastId = ids[ids.length - 1];

    // All but the last should be stale
    const staleIds = ids.slice(0, -1);
    staleIds.forEach((id) => {
      expect(isStaleRequest(id)).toBe(true);
    });

    // Only the last is active
    expect(isStaleRequest(lastId)).toBe(false);
  });

  it('each new nextRequestId call immediately invalidates the previous', () => {
    const { nextRequestId, isStaleRequest } = useRequestGuard();

    let prev = nextRequestId();
    for (let i = 0; i < 10; i++) {
      const next = nextRequestId();
      // As soon as we fire next, prev becomes stale
      expect(isStaleRequest(prev)).toBe(true);
      expect(isStaleRequest(next)).toBe(false);
      prev = next;
    }
  });

  it('multiple guards are independent of each other', () => {
    const guard1 = useRequestGuard();
    const guard2 = useRequestGuard();

    const g1id1 = guard1.nextRequestId();
    guard1.nextRequestId(); // advance guard1

    const g2id1 = guard2.nextRequestId(); // guard2 is still on 1

    // g1 id1 is stale in guard1
    expect(guard1.isStaleRequest(g1id1)).toBe(true);

    // g2 id1 is still current in guard2
    expect(guard2.isStaleRequest(g2id1)).toBe(false);
  });
});
