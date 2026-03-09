export function parseTokenList(input) {
  if (!input) {
    return [];
  }
  const seen = new Set();
  const tokens = [];
  String(input)
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .forEach((item) => {
      if (seen.has(item)) {
        return;
      }
      seen.add(item);
      tokens.push(item);
    });
  return tokens;
}

export function toQueryParams(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value === null || value === undefined || value === '') {
      return;
    }
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== null && item !== undefined && item !== '') {
          params.append(key, String(item));
        }
      });
      return;
    }
    params.set(key, String(value));
  });
  return params;
}

export function buildDrilldownNotice(matchStatus, fallbackReason = '') {
  const normalized = String(matchStatus || '').toLowerCase();
  if (normalized === 'exact') {
    return '';
  }
  if (normalized === 'partial') {
    if (fallbackReason === 'reason_unmapped') {
      return '原因碼未完整映射，已以可用條件開啟報廢頁面。';
    }
    return '僅取得部分映射，請在報廢頁面進一步確認。';
  }
  return '未找到對應報廢明細，已帶入基礎條件供人工追溯。';
}
