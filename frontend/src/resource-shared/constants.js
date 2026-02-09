export const STATUS_DISPLAY_MAP = Object.freeze({
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

export const STATUS_AGGREGATION = Object.freeze({
  PM: 'UDT',
  BKD: 'UDT',
  ENG: 'EGT',
  OFF: 'NST',
});

export const STATUS_COLORS = Object.freeze({
  PRD: '#22c55e',
  SBY: '#3b82f6',
  UDT: '#ef4444',
  SDT: '#f59e0b',
  EGT: '#8b5cf6',
  NST: '#64748b',
  OTHER: '#94a3b8',
});

export const OU_BADGE_THRESHOLDS = Object.freeze({
  high: 80,
  medium: 50,
  low: 0,
});

export const MATRIX_STATUS_COLUMNS = Object.freeze(['PRD', 'SBY', 'UDT', 'SDT', 'EGT', 'NST', 'OTHER']);

export function normalizeStatus(rawStatus) {
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

export function resolveOuBadgeClass(ouPct) {
  const value = Number(ouPct || 0);
  if (value >= OU_BADGE_THRESHOLDS.high) {
    return 'high';
  }
  if (value >= OU_BADGE_THRESHOLDS.medium) {
    return 'medium';
  }
  return 'low';
}

export function getStatusDisplay(status, fallback = '--') {
  const normalized = String(status || '').trim().toUpperCase();
  if (!normalized) {
    return fallback;
  }
  return STATUS_DISPLAY_MAP[normalized] || normalized;
}
