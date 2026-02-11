export function readQueryState(keys = []) {
  const params = new URLSearchParams(window.location.search);
  const state = {};
  keys.forEach((key) => {
    state[key] = params.get(key) || '';
  });
  return state;
}

export function writeQueryState(nextState = {}) {
  const params = new URLSearchParams(window.location.search);
  Object.entries(nextState).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      params.delete(key);
      return;
    }
    params.set(key, String(value));
  });

  const nextQuery = params.toString();
  const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ''}`;
  window.history.replaceState({}, '', nextUrl);
}
