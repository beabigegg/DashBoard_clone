export type EapAlarmSpoolResponse =
  | { kind: 'cache-hit'; queryId: string }
  | { kind: 'async'; jobId: string; queryId: string; statusUrl: string }
  | { kind: 'unexpected' };

function nonEmptyString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

/**
 * Normalize the two successful POST /api/eap-alarm/spool response shapes.
 * A warm spool is returned synchronously (200, async=false), while a cold
 * spool is queued (202, async=true) and must be polled.
 */
export function classifyEapAlarmSpoolResponse(response: unknown): EapAlarmSpoolResponse {
  const root = (response ?? {}) as Record<string, unknown>;
  const data = (root.data ?? {}) as Record<string, unknown>;
  const queryId = nonEmptyString(data.query_id);

  if (data.async === false && queryId) {
    return { kind: 'cache-hit', queryId };
  }

  const jobId = nonEmptyString(data.job_id);
  if (root._status === 202 || data.async === true || jobId) {
    const statusUrl =
      nonEmptyString(data.status_url) ||
      `/api/eap-alarm/spool/status?query_id=${encodeURIComponent(queryId)}`;
    return { kind: 'async', jobId, queryId, statusUrl };
  }

  return { kind: 'unexpected' };
}
