/**
 * Risk score and risk level calculation — mirrors backend yield_alert_sql_runtime.py.
 *
 * Formula (identical to DuckDB SQL in _query_alerts):
 *   risk_score = max(0, threshold - yield_pct) + min(max(scrap_qty, 0), 200) / 20
 *
 * Risk level thresholds:
 *   high   : yield_pct < threshold - 2  OR  scrap_qty >= 100
 *   medium : yield_pct < threshold       OR  scrap_qty >= 20
 *   low    : otherwise
 */

/**
 * Calculate the risk score for a single alert group.
 *
 * @param {number} yieldPct   - Yield percentage (0–100)
 * @param {number} scrapQty   - Absolute scrap quantity
 * @param {number} threshold  - Risk threshold (e.g. 98.5)
 * @returns {number} risk_score, rounded to 4 decimal places
 */
export function calcRiskScore(yieldPct, scrapQty, threshold) {
  const yp = Number(yieldPct);
  const sq = Number(scrapQty);
  const th = Number(threshold);
  const gapPenalty = Math.max(0, th - yp);
  const scrapPenalty = Math.min(Math.max(sq, 0), 200) / 20;
  return Math.round((gapPenalty + scrapPenalty) * 10000) / 10000;
}

/**
 * Determine the risk level for a single alert group.
 *
 * @param {number} yieldPct   - Yield percentage (0–100)
 * @param {number} scrapQty   - Absolute scrap quantity
 * @param {number} threshold  - Risk threshold (e.g. 98.5)
 * @returns {'high'|'medium'|'low'}
 */
export function calcRiskLevel(yieldPct, scrapQty, threshold) {
  const yp = Number(yieldPct);
  const sq = Number(scrapQty);
  const th = Number(threshold);
  if (yp < th - 2 || sq >= 100) return 'high';
  if (yp < th     || sq >= 20)  return 'medium';
  return 'low';
}
