export function groupBy(items, keySelector) {
  return items.reduce((acc, item) => {
    const key = keySelector(item);
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(item);
    return acc;
  }, {});
}

export function sortBy(items, keySelector, direction = 'asc') {
  const sign = direction === 'desc' ? -1 : 1;
  return [...items].sort((left, right) => {
    const a = keySelector(left);
    const b = keySelector(right);
    if (a === b) return 0;
    return a > b ? sign : -sign;
  });
}

export function toggleTreeState(state, key) {
  state[key] = !state[key];
  return state[key];
}

export function setTreeStateBulk(state, keys, expanded) {
  keys.forEach((key) => {
    state[key] = expanded;
  });
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function safeText(value, fallback = '') {
  return value === null || value === undefined ? fallback : String(value);
}
