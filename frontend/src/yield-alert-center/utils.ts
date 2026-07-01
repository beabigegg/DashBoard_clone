// ERP_WIP_MOVETXN.TRANSACTION_QUANTITY / SCRAP_QUANTITY are stored in K-PCS
// (thousand pcs); every value is an exact multiple of 0.001 (1 pcs). Convert
// to real pcs before displaying any absolute quantity to the user.
export const KPCS_TO_PCS = 1000;

export function toPcs(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n * KPCS_TO_PCS : 0;
}

export function parseTokenList(input: unknown): string[] {
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

export function toQueryParams(filters: Record<string, unknown> = {}): URLSearchParams {
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

export function buildDrilldownNotice(matchStatus: unknown, fallbackReason: string = ''): string {
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
