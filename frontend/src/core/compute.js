function round1(value) {
  const scaled = Number(value) * 10;
  const sign = Math.sign(scaled) || 1;
  const abs = Math.abs(scaled);
  const floor = Math.floor(abs);
  const diff = abs - floor;
  const epsilon = 1e-9;

  let rounded;
  if (diff > 0.5 + epsilon) {
    rounded = floor + 1;
  } else if (diff < 0.5 - epsilon) {
    rounded = floor;
  } else {
    // Match Python round(..., 1): banker's rounding (half to even).
    rounded = floor % 2 === 0 ? floor : floor + 1;
  }

  return (sign * rounded) / 10;
}

export function calcOuPct(prd, sby, udt, sdt, egt) {
  const denominator = Number(prd) + Number(sby) + Number(udt) + Number(sdt) + Number(egt);
  if (denominator <= 0) return 0;
  return round1((Number(prd) / denominator) * 100);
}

export function calcAvailabilityPct(prd, sby, udt, sdt, egt, nst) {
  const numerator = Number(prd) + Number(sby) + Number(egt);
  const denominator = numerator + Number(sdt) + Number(udt) + Number(nst);
  if (denominator <= 0) return 0;
  return round1((numerator / denominator) * 100);
}

export function calcStatusPct(value, total) {
  if (Number(total) <= 0) return 0;
  return round1((Number(value) / Number(total)) * 100);
}

export function calcYieldPct(trackout, ng) {
  const t = Number(trackout || 0);
  const n = Number(ng || 0);
  const denom = t + n;
  if (denom <= 0) return 0;
  return round1((t / denom) * 100);
}

export function calcOeePct(availability, yieldPct) {
  return round1((Number(availability || 0) * Number(yieldPct || 0)) / 100);
}

export function buildResourceKpiFromHours(hours = {}) {
  const prd = Number(hours.prd_hours || 0);
  const sby = Number(hours.sby_hours || 0);
  const udt = Number(hours.udt_hours || 0);
  const sdt = Number(hours.sdt_hours || 0);
  const egt = Number(hours.egt_hours || 0);
  const nst = Number(hours.nst_hours || 0);
  const total = prd + sby + udt + sdt + egt + nst;

  const trackout_qty = Number(hours.trackout_qty || 0);
  const ng_qty = Number(hours.ng_qty || 0);
  const availability_pct = calcAvailabilityPct(prd, sby, udt, sdt, egt, nst);
  const yield_pct = calcYieldPct(trackout_qty, ng_qty);
  const oee_pct = calcOeePct(availability_pct, yield_pct);

  return {
    ou_pct: calcOuPct(prd, sby, udt, sdt, egt),
    availability_pct,
    oee_pct,
    yield_pct,
    trackout_qty,
    ng_qty,
    prd_pct: calcStatusPct(prd, total),
    sby_pct: calcStatusPct(sby, total),
    udt_pct: calcStatusPct(udt, total),
    sdt_pct: calcStatusPct(sdt, total),
    egt_pct: calcStatusPct(egt, total),
    nst_pct: calcStatusPct(nst, total)
  };
}
