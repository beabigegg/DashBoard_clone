import { describe, it, expect } from 'vitest';
import { useViewStaleness } from '../useViewStaleness';

describe('useViewStaleness', () => {
  it('treats the latest request id for a key as fresh', () => {
    const { nextRequestId, isStaleRequest } = useViewStaleness(['summary']);
    const id = nextRequestId('summary');
    expect(isStaleRequest('summary', id)).toBe(false);
  });

  it('marks an older request stale once a newer one is issued for the same key', () => {
    const { nextRequestId, isStaleRequest } = useViewStaleness();
    const first = nextRequestId('detail');
    const second = nextRequestId('detail');
    expect(isStaleRequest('detail', first)).toBe(true);
    expect(isStaleRequest('detail', second)).toBe(false);
  });

  it('keeps per-key counters independent (the shared-counter bug it exists to prevent)', () => {
    const { nextRequestId, isStaleRequest } = useViewStaleness(['summary', 'pareto', 'trend']);
    // Simulate a fan-out: each endpoint issues its own request.
    const summaryId = nextRequestId('summary');
    const paretoId = nextRequestId('pareto');
    const trendId = nextRequestId('trend');
    // A second 'summary' fetch supersedes only summary — NOT pareto/trend.
    nextRequestId('summary');
    expect(isStaleRequest('summary', summaryId)).toBe(true);
    expect(isStaleRequest('pareto', paretoId)).toBe(false);
    expect(isStaleRequest('trend', trendId)).toBe(false);
  });

  it('handles keys lazily — an unseen key is safe and starts fresh', () => {
    const { nextRequestId, isStaleRequest } = useViewStaleness();
    // Never registered up-front.
    const id = nextRequestId('lots');
    expect(id).toBe(1);
    expect(isStaleRequest('lots', id)).toBe(false);
    // An id that was never issued for the key is stale.
    expect(isStaleRequest('lots', 999)).toBe(true);
  });

  it('reset(key) makes the previously-latest id stale', () => {
    const { nextRequestId, isStaleRequest, reset } = useViewStaleness(['summary']);
    const id = nextRequestId('summary');
    reset('summary');
    expect(isStaleRequest('summary', id)).toBe(true);
  });

  it('reset() with no argument resets every known key', () => {
    const { nextRequestId, isStaleRequest, reset } = useViewStaleness(['a', 'b']);
    const a = nextRequestId('a');
    const b = nextRequestId('b');
    reset();
    expect(isStaleRequest('a', a)).toBe(true);
    expect(isStaleRequest('b', b)).toBe(true);
  });
});
