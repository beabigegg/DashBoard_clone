export type QueryStateRecord = Record<string, string>;

export function readQueryState(keys: string[] = []): QueryStateRecord {
  const params = new URLSearchParams(window.location.search);
  const state: QueryStateRecord = {};
  keys.forEach((key) => {
    state[key] = params.get(key) || '';
  });
  return state;
}

export function writeQueryState(nextState: Record<string, unknown> = {}): void {
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
