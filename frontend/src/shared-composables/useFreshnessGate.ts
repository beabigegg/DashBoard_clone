/**
 * Shared factory for `useAutoRefresh`'s `shouldRefresh` gate: turns a cheap
 * "what's the current freshness token" probe into a stateful predicate that
 * only reports `true` once the token actually changes since the last time
 * the caller's own data load observed one (see `markFresh`).
 *
 * `fetchToken` should hit a lightweight, decoupled signal (e.g. `/health`'s
 * cache metadata, or a small metadata-only endpoint) — never the same
 * expensive endpoint `onRefresh` re-fetches, or the gate provides no savings.
 */

export interface FreshnessGate {
  /** Pass as `useAutoRefresh({ shouldRefresh })`. */
  shouldRefresh: () => Promise<boolean>;
  /**
   * Seed (or re-seed) the baseline token from a value the caller already
   * knows is current — call this right after every successful real data
   * load (initial mount included) using that load's own freshness field, so
   * the first scheduled check doesn't compare against a coincidentally
   * later token and misses/misfires.
   */
  markFresh: (token: string | null | undefined) => void;
  /**
   * Convenience for the common case where the caller's own data-load
   * response does NOT carry the same freshness field `fetchToken` polls
   * (e.g. the page's data endpoint returns a business-date field while the
   * freshness probe reads a separate cache-write-time field) — seeds the
   * baseline by calling `fetchToken` once directly, right after the
   * initial load completes.
   */
  seed: () => Promise<void>;
}

export function createFreshnessGate(fetchToken: () => Promise<string | null | undefined>): FreshnessGate {
  let lastToken: string | null = null;

  async function shouldRefresh(): Promise<boolean> {
    const token = await fetchToken();
    if (!token) {
      // Unknown freshness (e.g. health check failed) — don't force a refresh.
      return false;
    }
    if (lastToken === null) {
      lastToken = token;
      return false;
    }
    if (token !== lastToken) {
      lastToken = token;
      return true;
    }
    return false;
  }

  function markFresh(token: string | null | undefined): void {
    if (token) {
      lastToken = token;
    }
  }

  async function seed(): Promise<void> {
    markFresh(await fetchToken());
  }

  return { shouldRefresh, markFresh, seed };
}
