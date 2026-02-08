function toTrimmedString(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).trim();
}

export function normalizeStatusFilter(statusFilter) {
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

export function buildWipOverviewQueryParams(filters = {}, statusFilter = null) {
  const params = {};
  const workorder = toTrimmedString(filters.workorder);
  const lotid = toTrimmedString(filters.lotid);
  const pkg = toTrimmedString(filters.package);
  const type = toTrimmedString(filters.type);

  if (workorder) params.workorder = workorder;
  if (lotid) params.lotid = lotid;
  if (pkg) params.package = pkg;
  if (type) params.type = type;

  return { ...params, ...normalizeStatusFilter(statusFilter) };
}

export function buildWipDetailQueryParams({
  page,
  pageSize,
  filters = {},
  statusFilter = null,
}) {
  return {
    page,
    page_size: pageSize,
    ...buildWipOverviewQueryParams(filters, statusFilter),
  };
}

export function splitHoldByType(data) {
  const items = Array.isArray(data?.items) ? data.items : [];
  const quality = items.filter((item) => item?.holdType === 'quality');
  const nonQuality = items.filter((item) => item?.holdType !== 'quality');
  return { quality, nonQuality };
}

export function prepareParetoData(items) {
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
