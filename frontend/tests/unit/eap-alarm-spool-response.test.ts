import { describe, expect, it } from 'vitest';

import { classifyEapAlarmSpoolResponse } from '../../src/eap-alarm/spoolResponse';

describe('EAP ALARM spool response classification', () => {
  it('treats a warm spool response as an immediately loadable cache hit', () => {
    expect(classifyEapAlarmSpoolResponse({
      success: true,
      data: {
        async: false,
        query_id: 'eap_alarm_2026-07-07_2026-07-13_37028429_v5',
      },
    })).toEqual({
      kind: 'cache-hit',
      queryId: 'eap_alarm_2026-07-07_2026-07-13_37028429_v5',
    });
  });

  it('keeps cold spool responses on the async polling path', () => {
    expect(classifyEapAlarmSpoolResponse({
      success: true,
      data: {
        async: true,
        job_id: 'eap-alarm-job-001',
        query_id: 'eap-alarm-query-001',
        status_url: '/api/eap-alarm/spool/status?job_id=eap-alarm-job-001',
      },
    })).toEqual({
      kind: 'async',
      jobId: 'eap-alarm-job-001',
      queryId: 'eap-alarm-query-001',
      statusUrl: '/api/eap-alarm/spool/status?job_id=eap-alarm-job-001',
    });
  });

  it('rejects a malformed cache-hit response without a query id', () => {
    expect(classifyEapAlarmSpoolResponse({
      success: true,
      data: { async: false },
    })).toEqual({ kind: 'unexpected' });
  });
});
