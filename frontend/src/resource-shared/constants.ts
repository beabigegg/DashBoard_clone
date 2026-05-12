export const STATUS_DISPLAY_MAP: Readonly<Record<string, string>> = Object.freeze({
  PRD: '生產中',
  SBY: '待機',
  UDT: '非計畫停機',
  SDT: '計畫停機',
  EGT: '工程',
  NST: '未排程',
  PM: '保養',
  BKD: '故障',
  ENG: '工程',
  OFF: '關機',
  OTHER: '其他',
});

export const STATUS_AGGREGATION: Readonly<Record<string, string>> = Object.freeze({
  PM: 'UDT',
  BKD: 'UDT',
  ENG: 'EGT',
  OFF: 'NST',
});

export const STATUS_COLORS: Readonly<Record<string, string>> = Object.freeze({
  PRD: 'var(--color-token-h22c55e)',
  SBY: 'var(--color-token-h3b82f6)',
  UDT: 'var(--color-token-hef4444)',
  SDT: 'var(--color-token-hf59e0b)',
  EGT: 'var(--color-token-h8b5cf6)',
  NST: 'var(--color-token-h64748b)',
  OTHER: 'var(--color-token-h94a3b8)',
});

export const OU_BADGE_THRESHOLDS: Readonly<{ high: number; medium: number; low: number }> =
  Object.freeze({
    high: 80,
    medium: 50,
    low: 0,
  });

export const MATRIX_STATUS_COLUMNS: readonly string[] = Object.freeze([
  'PRD',
  'SBY',
  'UDT',
  'SDT',
  'EGT',
  'NST',
  'OTHER',
]);

export function normalizeStatus(rawStatus: unknown): string {
  const status = String(rawStatus || '').trim().toUpperCase();
  if (!status) {
    return 'OTHER';
  }

  const aggregated = STATUS_AGGREGATION[status] || status;
  if (MATRIX_STATUS_COLUMNS.includes(aggregated)) {
    return aggregated;
  }
  return 'OTHER';
}

export function resolveOuBadgeClass(ouPct: unknown): 'high' | 'medium' | 'low' {
  const value = Number(ouPct || 0);
  if (value >= OU_BADGE_THRESHOLDS.high) {
    return 'high';
  }
  if (value >= OU_BADGE_THRESHOLDS.medium) {
    return 'medium';
  }
  return 'low';
}

export function getStatusDisplay(status: unknown, fallback = '--'): string {
  const normalized = String(status || '').trim().toUpperCase();
  if (!normalized) {
    return fallback;
  }
  return STATUS_DISPLAY_MAP[normalized] || normalized;
}
