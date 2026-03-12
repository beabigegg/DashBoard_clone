export function useUrlSync() {
  function syncToUrl(state) {
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

  function readFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const state = {};
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
