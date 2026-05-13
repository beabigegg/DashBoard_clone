function toTrimmedString(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).trim();
}

function normalizeFilterValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((item) => toTrimmedString(item))
      .filter((item) => item.length > 0)
      .join(',');
  }
  return toTrimmedString(value);
}

export interface WipStatusFilterResult {
  status?: string;
  hold_type?: string;
}

export function normalizeStatusFilter(statusFilter: string | null | undefined): WipStatusFilterResult {
  if (!statusFilter) {
    return {};
  }
  if (statusFilter === 'quality-hold') {
    return { status: 'HOLD', hold_type: 'quality' };
  }
  if (statusFilter === 'non-quality-hold') {
    return { status: 'HOLD', hold_type: 'non-quality' };
  }
  return { status: String(statusFilter).toUpperCase() };
}

export interface WipFilters {
  workorder?: unknown;
  lotid?: unknown;
  package?: unknown;
  type?: unknown;
  firstname?: unknown;
  waferdesc?: unknown;
  workflow?: unknown;
  bop?: unknown;
  pjFunction?: unknown;
  [key: string]: unknown;
}

export type WipOverviewQueryParams = Record<string, string>;

export function buildWipOverviewQueryParams(
  filters: WipFilters = {},
  statusFilter: string | null = null
): WipOverviewQueryParams {
  const params: WipOverviewQueryParams = {};
  const workorder = normalizeFilterValue(filters.workorder);
  const lotid = normalizeFilterValue(filters.lotid);
  const pkg = normalizeFilterValue(filters.package);
  const type = normalizeFilterValue(filters.type);
  const firstname = normalizeFilterValue(filters.firstname);
  const waferdesc = normalizeFilterValue(filters.waferdesc);
  const workflow = normalizeFilterValue(filters.workflow);
  const bop = normalizeFilterValue(filters.bop);
  const pjFunction = normalizeFilterValue(filters.pjFunction);

  if (workorder) params.workorder = workorder;
  if (lotid) params.lotid = lotid;
  if (pkg) params.package = pkg;
  if (type) params.type = type;
  if (firstname) params.firstname = firstname;
  if (waferdesc) params.waferdesc = waferdesc;
  if (workflow) params.workflow = workflow;
  if (bop) params.bop = bop;
  if (pjFunction) params.pj_function = pjFunction;

  return { ...params, ...normalizeStatusFilter(statusFilter) };
}

export interface WipDetailQueryOptions {
  page: number;
  pageSize: number;
  filters?: WipFilters;
  statusFilter?: string | null;
}

export function buildWipDetailQueryParams(
  options: WipDetailQueryOptions
): Record<string, unknown> {
  const { page, pageSize, filters = {}, statusFilter = null } = options;
  return {
    page,
    page_size: pageSize,
    ...buildWipOverviewQueryParams(filters, statusFilter),
  };
}

export interface WipItem {
  holdType?: string;
  reason?: unknown;
  qty?: unknown;
  lots?: unknown;
  [key: string]: unknown;
}

export interface HoldSplit {
  quality: WipItem[];
  nonQuality: WipItem[];
}

export function splitHoldByType(data: { items?: WipItem[] } | null | undefined): HoldSplit {
  const items = Array.isArray(data?.items) ? data!.items : [];
  const quality = items.filter((item) => item?.holdType === 'quality');
  const nonQuality = items.filter((item) => item?.holdType !== 'quality');
  return { quality, nonQuality };
}

export interface ParetoData {
  reasons: string[];
  qtys: number[];
  lots: number[];
  cumulative: number[];
  totalQty: number;
  items: WipItem[];
}

export function prepareParetoData(items: WipItem[]): ParetoData {
  if (!Array.isArray(items) || items.length === 0) {
    return { reasons: [], qtys: [], lots: [], cumulative: [], totalQty: 0, items: [] };
  }

  const sorted = [...items].sort((a, b) => (Number(b?.qty) || 0) - (Number(a?.qty) || 0));
  const reasons = sorted.map((item) => toTrimmedString(item?.reason) || '未知');
  const qtys = sorted.map((item) => Number(item?.qty) || 0);
  const lots = sorted.map((item) => Number(item?.lots) || 0);
  const totalQty = qtys.reduce((sum, value) => sum + value, 0);

  let running = 0;
  const cumulative = qtys.map((qty) => {
    running += qty;
    if (totalQty <= 0) return 0;
    return Math.round((running / totalQty) * 100);
  });

  return { reasons, qtys, lots, cumulative, totalQty, items: sorted };
}
