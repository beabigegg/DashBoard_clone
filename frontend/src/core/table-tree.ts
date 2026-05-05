export function groupBy<T>(
  items: T[],
  keySelector: (item: T) => string
): Record<string, T[]> {
  return items.reduce<Record<string, T[]>>((acc, item) => {
    const key = keySelector(item);
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(item);
    return acc;
  }, {});
}

export function sortBy<T>(
  items: T[],
  keySelector: (item: T) => string | number,
  direction: 'asc' | 'desc' = 'asc'
): T[] {
  const sign = direction === 'desc' ? -1 : 1;
  return [...items].sort((left, right) => {
    const a = keySelector(left);
    const b = keySelector(right);
    if (a === b) return 0;
    return a > b ? sign : -sign;
  });
}

export function toggleTreeState(
  state: Record<string, boolean>,
  key: string
): boolean {
  state[key] = !state[key];
  return state[key];
}

export function setTreeStateBulk(
  state: Record<string, boolean>,
  keys: string[],
  expanded: boolean
): void {
  keys.forEach((key) => {
    state[key] = expanded;
  });
}

export function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function safeText(value: unknown, fallback = ''): string {
  return value === null || value === undefined ? fallback : String(value);
}
