export function normalizeText(value: unknown): string {
  return String(value || '').trim();
}

export function uniqueValues(values: unknown[] = []): string[] {
  const seen = new Set<string>();
  const list: string[] = [];
  values.forEach((value) => {
    const normalized = normalizeText(value);
    if (!normalized || seen.has(normalized)) {
      return;
    }
    seen.add(normalized);
    list.push(normalized);
  });
  return list;
}

export function parseInputValues(raw: unknown): string[] {
  return uniqueValues(String(raw || '').split(/[\n,]/));
}

export function parseArrayParam(params: URLSearchParams, key: string): string[] {
  const repeated = params.getAll(key).map((item) => normalizeText(item)).filter(Boolean);
  if (repeated.length > 0) {
    return uniqueValues(repeated);
  }
  const fallback = normalizeText(params.get(key));
  if (!fallback) {
    return [];
  }
  return uniqueValues(fallback.split(','));
}

export function toDateInputValue(value: unknown): string {
  if (!value) {
    return '';
  }
  const date = value instanceof Date ? value : new Date(value as string | number);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  return date.toISOString().slice(0, 10);
}

export function parseDateTime(value: unknown): Date | null {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const date = new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
}

export function formatDateTime(value: unknown): string {
  const date = parseDateTime(value);
  if (!date) {
    return '-';
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hour = String(date.getHours()).padStart(2, '0');
  const minute = String(date.getMinutes()).padStart(2, '0');
  const second = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return '-';
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toLocaleString() : '-';
  }
  return String(value);
}

export function hashColor(seed: unknown): string {
  const text = normalizeText(seed) || 'fallback';
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} 70% 52%)`;
}
