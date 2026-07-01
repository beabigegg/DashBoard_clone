export interface ViewStaleness {
  /** Bump and return the active request id for one endpoint key. */
  nextRequestId: (key: string) => number;
  /** True if `id` is no longer the latest request issued for `key`. */
  isStaleRequest: (key: string, id: number) => boolean;
  /** Reset one key (or all keys when called with no argument). */
  reset: (key?: string) => void;
}

/**
 * Per-endpoint request-staleness guard for multi-view fan-out fetches.
 *
 * Generalises {@link useRequestGuard} (a single shared counter) to N
 * independent endpoint keys, each with its own monotonically-increasing
 * counter. Use this whenever one user action triggers several concurrent
 * fetches (summary + pareto + trend + detail, matrix + lots, ...): a
 * fast-returning endpoint must not invalidate a slow sibling's in-flight
 * request, which is exactly the bug a single shared counter causes when a
 * fan-out resolves out of order.
 *
 * Usage:
 * ```ts
 * const { nextRequestId, isStaleRequest } = useViewStaleness(['summary', 'detail']);
 *
 * async function fetchSummary(params) {
 *   const rid = nextRequestId('summary');
 *   const data = await apiGet('/api/x/summary', params);
 *   if (isStaleRequest('summary', rid)) return; // a newer summary fetch superseded us
 *   summary.value = data;
 * }
 * ```
 *
 * Keys are created lazily, so the optional `keys` argument is only for
 * documentation / eager initialisation — passing an unknown key to
 * `nextRequestId` is always safe.
 */
export function useViewStaleness(keys: string[] = []): ViewStaleness {
  const ids: Record<string, number> = {};
  for (const k of keys) ids[k] = 0;

  function nextRequestId(key: string): number {
    ids[key] = (ids[key] ?? 0) + 1;
    return ids[key];
  }

  function isStaleRequest(key: string, id: number): boolean {
    return id !== (ids[key] ?? 0);
  }

  function reset(key?: string): void {
    if (key === undefined) {
      for (const k of Object.keys(ids)) ids[k] = 0;
    } else {
      ids[key] = 0;
    }
  }

  return { nextRequestId, isStaleRequest, reset };
}
