export interface UrlSyncState {
  [key: string]: unknown;
}

export interface UrlSync {
  syncToUrl: (state: UrlSyncState) => void;
  readFromUrl: () => UrlSyncState;
}

export function useUrlSync(): UrlSync {
  function syncToUrl(state: UrlSyncState): void {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(state)) {
      if (value === null || value === undefined || value === '') continue;
      if (Array.isArray(value)) {
        if (value.length > 0) params.set(key, JSON.stringify(value));
      } else {
        params.set(key, String(value));
      }
    }
    const search = params.toString();
    const newUrl = search
      ? `${window.location.pathname}?${search}`
      : window.location.pathname;
    window.history.replaceState(null, '', newUrl);
  }

  function readFromUrl(): UrlSyncState {
    const params = new URLSearchParams(window.location.search);
    const state: UrlSyncState = {};
    for (const [key, value] of params.entries()) {
      try {
        state[key] = JSON.parse(value);
      } catch {
        state[key] = value;
      }
    }
    return state;
  }

  return { syncToUrl, readFromUrl };
}
