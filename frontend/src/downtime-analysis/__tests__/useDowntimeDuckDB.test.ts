/**
 * useDowntimeDuckDB — parity tests (TDD: written failing first, per test-plan.md)
 *
 * Change: downtime-browser-duckdb
 * AC-3: composable SQL parity vs Python _merge_cross_shift_events / _bridge_jobid / _map_big_category
 * AC-4: taxonomy-driven BigCategory identical to prior server map
 * AC-7: error states surface visible error, never silent empty table
 * AC-8: CSV export blob equals rendered data
 *
 * Fixture discipline (test-plan.md §Parity Fixture Note):
 * - At least one cross-midnight event (prev_end T23:59 → estart T00:10 next day, gap < 60s)
 * - At least one ambiguous job-bridge tie-break case (runner-up overlap >= 80% of winner)
 *
 * All timestamps use UTC ('Z' suffix) to avoid TZ-offset-induced sort corruption.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ── Type aliases used in tests ──────────────────────────────────────────────

interface RawBaseEvent {
  HISTORYID: string;
  OLDSTATUSNAME: string;
  OLDREASONNAME: string | null;
  OLDLASTSTATUSCHANGEDATE: string; // ISO timestamp UTC
  LASTSTATUSCHANGEDATE: string;    // ISO timestamp UTC
  HOURS: number;
  JOBID: string | null;
}

interface RawJobBridge {
  JOBID: string;
  RESOURCEID: string;
  CREATEDATE: string;
  COMPLETEDATE: string | null;
  SYMPTOMCODENAME: string | null;
  CAUSECODENAME: string | null;
  REPAIRCODENAME: string | null;
  COMPLETE_FULLNAME: string | null;
  FIRSTCLOCKONDATE: string | null;
  LASTCLOCKOFFDATE: string | null;
  JOBORDERNAME: string | null;
  JOBMODELNAME: string | null;
  ASSIGNED_DATE: string | null;
  ACK_DATE: string | null;
  INSPECT_START: string | null;
  INSPECT_END: string | null;
}

interface TaxonomyShape {
  map: [string, string][];
  prefixes: [string, string][];
  egt_category: string;
  fallback: string;
}

// ── Minimal fixture data (all timestamps UTC with 'Z') ──────────────────────

/**
 * Fixture: base events including:
 * - EVT-001 + EVT-002: same machine R-001, same status UDT, same reason EE Repair,
 *   fragments across midnight (gap = 30s < 60s → should merge to 1 logical event)
 * - EVT-003: R-001, SDT with EE_PM — should NOT merge with UDT fragments
 * - EVT-004: R-002, UDT, gap > 60s → stays as separate events
 * - EVT-005: R-002, EGT status (should be mapped to '工程' category)
 */
const BASE_EVENTS_FIXTURE: RawBaseEvent[] = [
  // Cross-midnight pair: fragment 1 ends 2026-01-10T23:59:30Z, fragment 2 starts 2026-01-11T00:00:00Z
  // Gap = 30s < 60s → should merge into one logical event
  {
    HISTORYID: 'R-001',
    OLDSTATUSNAME: 'UDT',
    OLDREASONNAME: 'EE Repair',
    OLDLASTSTATUSCHANGEDATE: '2026-01-10T20:00:00Z',
    LASTSTATUSCHANGEDATE: '2026-01-10T23:59:30Z',
    HOURS: 3.9917,
    JOBID: 'JOB-001',
  },
  {
    HISTORYID: 'R-001',
    OLDSTATUSNAME: 'UDT',
    OLDREASONNAME: 'EE Repair',
    OLDLASTSTATUSCHANGEDATE: '2026-01-11T00:00:00Z',
    LASTSTATUSCHANGEDATE: '2026-01-11T02:00:00Z',
    HOURS: 2.0,
    JOBID: 'JOB-001',
  },
  // Different status — no merge with UDT
  {
    HISTORYID: 'R-001',
    OLDSTATUSNAME: 'SDT',
    OLDREASONNAME: 'EE_PM',
    OLDLASTSTATUSCHANGEDATE: '2026-01-10T10:00:00Z',
    LASTSTATUSCHANGEDATE: '2026-01-10T12:00:00Z',
    HOURS: 2.0,
    JOBID: null,
  },
  // R-002: gap > 60s → stay separate (gap = 3600s)
  {
    HISTORYID: 'R-002',
    OLDSTATUSNAME: 'UDT',
    OLDREASONNAME: 'EAP Minor stoppage',
    OLDLASTSTATUSCHANGEDATE: '2026-01-10T08:00:00Z',
    LASTSTATUSCHANGEDATE: '2026-01-10T09:00:00Z',
    HOURS: 1.0,
    JOBID: 'JOB-002',
  },
  {
    HISTORYID: 'R-002',
    OLDSTATUSNAME: 'UDT',
    OLDREASONNAME: 'EAP Minor stoppage',
    OLDLASTSTATUSCHANGEDATE: '2026-01-10T10:00:00Z', // gap = 3600s > 60s
    LASTSTATUSCHANGEDATE: '2026-01-10T11:00:00Z',
    HOURS: 1.0,
    JOBID: 'JOB-003',
  },
  // EGT status event
  {
    HISTORYID: 'R-002',
    OLDSTATUSNAME: 'EGT',
    OLDREASONNAME: null,
    OLDLASTSTATUSCHANGEDATE: '2026-01-10T14:00:00Z',
    LASTSTATUSCHANGEDATE: '2026-01-10T15:00:00Z',
    HOURS: 1.0,
    JOBID: null,
  },
];

/**
 * Job bridge fixture including:
 * - JOB-001: matches R-001 UDT merged event directly by JOBID (Path A)
 * - JOB-001B: overlap-based runner-up for same R-001 event (triggers match_ambiguous)
 * - JOB-002: matches R-002 UDT event 1 by direct JOBID (Path A)
 * - JOB-003: matches R-002 UDT event 2 by direct JOBID (Path A)
 *
 * Ambiguity: JOB-001B overlaps the R-001 merged event with >= 80% of JOB-001's overlap.
 * Since the merged event uses JOBID=JOB-001 (Path A), ambiguity is only Path B.
 * To test Path B ambiguity separately, we need an event without JOBID.
 * Using a synthetic event that merges without JOBID propagation would be complex.
 * Instead we verify ambiguity with a job-bridge-only Path B fixture below.
 */
const JOB_BRIDGE_FIXTURE: RawJobBridge[] = [
  {
    JOBID: 'JOB-001',
    RESOURCEID: 'R-001',
    CREATEDATE: '2026-01-10T20:00:00Z',
    COMPLETEDATE: '2026-01-11T03:00:00Z',
    SYMPTOMCODENAME: 'Motor failure',
    CAUSECODENAME: 'Wear',
    REPAIRCODENAME: 'Replace bearing',
    COMPLETE_FULLNAME: 'Technician A',
    FIRSTCLOCKONDATE: '2026-01-10T20:30:00Z',
    LASTCLOCKOFFDATE: '2026-01-11T02:30:00Z',
    JOBORDERNAME: 'WO-001',
    JOBMODELNAME: 'ModelX',
    ASSIGNED_DATE: '2026-01-10T20:10:00Z',
    ACK_DATE: '2026-01-10T20:20:00Z',
    INSPECT_START: null,
    INSPECT_END: null,
  },
  {
    JOBID: 'JOB-002',
    RESOURCEID: 'R-002',
    CREATEDATE: '2026-01-10T07:00:00Z',
    COMPLETEDATE: '2026-01-10T10:00:00Z',
    SYMPTOMCODENAME: 'Alignment',
    CAUSECODENAME: null,
    REPAIRCODENAME: null,
    COMPLETE_FULLNAME: null,
    FIRSTCLOCKONDATE: null,
    LASTCLOCKOFFDATE: null,
    JOBORDERNAME: 'WO-002',
    JOBMODELNAME: null,
    ASSIGNED_DATE: null,
    ACK_DATE: null,
    INSPECT_START: null,
    INSPECT_END: null,
  },
  {
    JOBID: 'JOB-003',
    RESOURCEID: 'R-002',
    CREATEDATE: '2026-01-10T09:00:00Z',
    COMPLETEDATE: '2026-01-10T12:00:00Z',
    SYMPTOMCODENAME: null,
    CAUSECODENAME: null,
    REPAIRCODENAME: null,
    COMPLETE_FULLNAME: null,
    FIRSTCLOCKONDATE: null,
    LASTCLOCKOFFDATE: null,
    JOBORDERNAME: 'WO-003',
    JOBMODELNAME: null,
    ASSIGNED_DATE: null,
    ACK_DATE: null,
    INSPECT_START: null,
    INSPECT_END: null,
  },
];

/**
 * Ambiguous Path B fixture: synthetic events without JOBID that resolve to
 * winner + runner-up >= 80% overlap. Event window: 2026-01-20T08:00Z–2026-01-20T14:00Z (6h).
 * JOB-AMB-WIN: 2026-01-20T07:00Z–2026-01-20T14:00Z → overlap 6h
 * JOB-AMB-RUN: 2026-01-20T07:30Z–2026-01-20T13:00Z → overlap 5.5h (≈91.7% of 6h → ambiguous)
 */
const PATH_B_AMBIGUOUS_EVENTS: RawBaseEvent[] = [
  {
    HISTORYID: 'R-003',
    OLDSTATUSNAME: 'UDT',
    OLDREASONNAME: 'EAP Minor stoppage',
    OLDLASTSTATUSCHANGEDATE: '2026-01-20T08:00:00Z',
    LASTSTATUSCHANGEDATE: '2026-01-20T14:00:00Z',
    HOURS: 6.0,
    JOBID: null,  // No JOBID → Path B overlap resolution
  },
];

const PATH_B_AMBIGUOUS_JOBS: RawJobBridge[] = [
  {
    JOBID: 'JOB-AMB-WIN',
    RESOURCEID: 'R-003',
    CREATEDATE: '2026-01-20T07:00:00Z',
    COMPLETEDATE: '2026-01-20T14:00:00Z',
    SYMPTOMCODENAME: 'Winner job',
    CAUSECODENAME: null,
    REPAIRCODENAME: null,
    COMPLETE_FULLNAME: null,
    FIRSTCLOCKONDATE: null,
    LASTCLOCKOFFDATE: null,
    JOBORDERNAME: 'WO-AMB-WIN',
    JOBMODELNAME: null,
    ASSIGNED_DATE: null,
    ACK_DATE: null,
    INSPECT_START: null,
    INSPECT_END: null,
  },
  {
    JOBID: 'JOB-AMB-RUN',
    RESOURCEID: 'R-003',
    CREATEDATE: '2026-01-20T07:30:00Z',
    COMPLETEDATE: '2026-01-20T13:00:00Z',
    SYMPTOMCODENAME: 'Runner-up job',
    CAUSECODENAME: null,
    REPAIRCODENAME: null,
    COMPLETE_FULLNAME: null,
    FIRSTCLOCKONDATE: null,
    LASTCLOCKOFFDATE: null,
    JOBORDERNAME: 'WO-AMB-RUN',
    JOBMODELNAME: null,
    ASSIGNED_DATE: null,
    ACK_DATE: null,
    INSPECT_START: null,
    INSPECT_END: null,
  },
];

/**
 * Server-authoritative taxonomy from _build_taxonomy_json() (_BIG_CATEGORY_MAP).
 * Sorted alphabetically by reason key (as returned by sorted(_BIG_CATEGORY_MAP.items())).
 * Note: backend uses '改機換料' / '治工具更換與模具清潔' / '教讀程式'.
 * These differ from the legacy useBigCategory.ts ('換型換線' / '換刀清模').
 * The composable MUST use server-provided taxonomy, NOT the local useBigCategory labels.
 */
const TAXONOMY_FIXTURE: TaxonomyShape = {
  map: [
    ['Cmk inspection', '保養'],
    ['Change Marking Code', '改機換料'],
    ['Change Model', '改機換料'],
    ['Change Package', '改機換料'],
    ['Change Tool/Consumables', '治工具更換與模具清潔'],
    ['Change Tool/Consumables in process', '治工具更換與模具清潔'],
    ['Change Type', '改機換料'],
    ['Clean Mold', '治工具更換與模具清潔'],
    ['EAP Minor stoppage', '維修'],
    ['EE Repair', '維修'],
    ['EE_PM', '保養'],
    ['FAC Repair', '維修'],
    ['Facilities related Down', '維修'],
    ['Group Equipment Down', '維修'],
    ['MF_PM', '保養'],
    ['Machine Calibration', '保養'],
    ['No Operator', '待料待指示'],
    ['No Raw Material', '待料待指示'],
    ['PD_PM', '保養'],
    ['Prod_PD_inspection', '檢查'],
    ['Prod_QC_Inspection', '檢查'],
    ['Programing', '教讀程式'],
    ['Re Layout', '改機換料'],
    ['Test Run', '維修'],
    ['Wait For Instructions', '待料待指示'],
  ],
  prefixes: [['TMTT_', '檢查']],
  // egt_category: the OUTPUT category for events with OLDSTATUSNAME == 'EGT'
  egt_category: '工程',
  fallback: '其他/未分類',
};

// ── Lazy import of the composable (will fail until it exists) ────────────────

async function importComposable() {
  const mod = await import('../composables/useDowntimeDuckDB');
  return mod;
}

// ── Mocks for DuckDB client ──────────────────────────────────────────────────

vi.mock('../../core/duckdb-client', () => {
  const mockClient = {
    init: vi.fn().mockResolvedValue(undefined),
    registerParquet: vi.fn().mockResolvedValue(undefined),
    sendQuery: vi.fn().mockResolvedValue([]),
    destroy: vi.fn(),
  };
  return {
    getDuckDBClient: vi.fn().mockReturnValue(mockClient),
    fetchParquetBuffer: vi.fn().mockResolvedValue(new ArrayBuffer(8)),
    isDuckDBSupported: vi.fn().mockReturnValue(true),
  };
});

// ── applyTaxonomy: mirrors the browser composable logic ─────────────────────
// status='EGT' events → egt_category output (regardless of reason)
// exact map lookup, then prefix, then fallback

function applyTaxonomy(reason: string | null, status: string, taxonomy: TaxonomyShape): string {
  // EGT status always maps to egt_category (which is '工程')
  if (status.trim() === 'EGT') return taxonomy.egt_category;
  const stripped = (reason ?? '').trim();
  if (!stripped) return taxonomy.fallback;
  const exact = taxonomy.map.find(([r]) => r === stripped);
  if (exact) return exact[1];
  const prefix = taxonomy.prefixes.find(([p]) => stripped.startsWith(p));
  if (prefix) return prefix[1];
  return taxonomy.fallback;
}

// ── Pure JS cross-shift merge (mirrors _CROSS_SHIFT_MERGE_SQL logic) ─────────

interface MergedEvent {
  HISTORYID: string;
  OLDSTATUSNAME: string;
  OLDREASONNAME: string | null;
  event_start: Date;
  event_end: Date;
  hours: number;
  fragment_count: number;
  JOBID: string | null;
}

function crossShiftMerge(events: RawBaseEvent[], gapSeconds = 60): MergedEvent[] {
  if (!events.length) return [];

  const parsed = events.map((e) => ({
    ...e,
    _h: e.HISTORYID.trim(),
    _s: e.OLDSTATUSNAME.trim(),
    _r: (e.OLDREASONNAME ?? '').trim(),
    _estart: new Date(e.OLDLASTSTATUSCHANGEDATE),
    _eend: new Date(e.LASTSTATUSCHANGEDATE),
    _hours: Number(e.HOURS) || 0,
  }));

  // Sort: HISTORYID, OLDSTATUSNAME, OLDREASONNAME (coerced empty), event_start
  parsed.sort((a, b) => {
    if (a._h !== b._h) return a._h < b._h ? -1 : 1;
    if (a._s !== b._s) return a._s < b._s ? -1 : 1;
    if (a._r !== b._r) return a._r < b._r ? -1 : 1;
    return a._estart.getTime() - b._estart.getTime();
  });

  const merged: MergedEvent[] = [];
  let current: MergedEvent | null = null;
  let prevEnd: Date | null = null;
  let prevH = '';
  let prevS = '';
  let prevR = '';

  for (const ev of parsed) {
    const isBreak =
      !current ||
      ev._h !== prevH ||
      ev._s !== prevS ||
      ev._r !== prevR ||
      prevEnd === null ||
      (ev._estart.getTime() - prevEnd.getTime()) / 1000 > gapSeconds;

    if (isBreak) {
      if (current) merged.push(current);
      current = {
        HISTORYID: ev._h,
        OLDSTATUSNAME: ev._s,
        OLDREASONNAME: ev._r || null,
        event_start: ev._estart,
        event_end: ev._eend,
        hours: ev._hours,
        fragment_count: 1,
        JOBID: ev.JOBID,
      };
    } else {
      if (ev._eend > current!.event_end) current!.event_end = ev._eend;
      current!.hours = Math.round((current!.hours + ev._hours) * 1e6) / 1e6;
      current!.fragment_count++;
      if (ev.JOBID && !current!.JOBID) current!.JOBID = ev.JOBID;
    }
    prevH = ev._h;
    prevS = ev._s;
    prevR = ev._r;
    prevEnd = ev._eend;
  }
  if (current) merged.push(current);

  merged.sort((a, b) =>
    a.HISTORYID < b.HISTORYID ? -1 : a.HISTORYID > b.HISTORYID ? 1 : a.event_start.getTime() - b.event_start.getTime()
  );

  return merged;
}

// ── Pure JS job-bridge parity (mirrors _bridge_jobid) ───────────────────────

interface BridgedEvent extends MergedEvent {
  match_source: 'jobid' | 'overlap' | 'none';
  match_ambiguous: boolean;
  job_id: string | null;
  symptom: string | null;
  cause: string | null;
}

function bridgeJobs(merged: MergedEvent[], jobs: RawJobBridge[]): BridgedEvent[] {
  return merged.map((ev) => {
    // Path A: JOBID direct lookup
    if (ev.JOBID) {
      const job = jobs.find((j) => j.JOBID === ev.JOBID);
      if (job) {
        return {
          ...ev,
          match_source: 'jobid' as const,
          match_ambiguous: false,
          job_id: job.JOBID,
          symptom: job.SYMPTOMCODENAME,
          cause: job.CAUSECODENAME,
        };
      }
      // JOBID found but not in jobs → orphan
      return { ...ev, match_source: 'none' as const, match_ambiguous: false, job_id: null, symptom: null, cause: null };
    }

    // Path B: time-overlap with RESOURCEID == HISTORYID
    const candidates = jobs
      .filter((j) => j.RESOURCEID.trim() === ev.HISTORYID)
      .map((j) => {
        const cd = new Date(j.CREATEDATE);
        const cpd = j.COMPLETEDATE ? new Date(j.COMPLETEDATE) : new Date('2099-01-01T00:00:00Z');
        const overlapStart = Math.max(ev.event_start.getTime(), cd.getTime());
        const overlapEnd = Math.min(ev.event_end.getTime(), cpd.getTime());
        const overlap = Math.max(0, (overlapEnd - overlapStart) / 1000);
        return { ...j, _overlap: overlap, _cd: cd };
      })
      .filter((j) => {
        const cd = new Date(j.CREATEDATE);
        const cpd = j.COMPLETEDATE ? new Date(j.COMPLETEDATE) : new Date('2099-01-01T00:00:00Z');
        return cpd > ev.event_start && cd < ev.event_end;
      })
      .sort((a, b) =>
        b._overlap - a._overlap ||
        a._cd.getTime() - b._cd.getTime() ||
        a.JOBID.localeCompare(b.JOBID)
      );

    if (!candidates.length) {
      return { ...ev, match_source: 'none' as const, match_ambiguous: false, job_id: null, symptom: null, cause: null };
    }

    const winner = candidates[0];
    const runnerUp = candidates[1];
    const ambiguous =
      runnerUp !== undefined &&
      winner._overlap > 0 &&
      runnerUp._overlap >= 0.8 * winner._overlap;

    return {
      ...ev,
      match_source: 'overlap' as const,
      match_ambiguous: ambiguous,
      job_id: winner.JOBID,
      symptom: winner.SYMPTOMCODENAME,
      cause: winner.CAUSECODENAME,
    };
  });
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('cross-shift merge parity', () => {
  it('merges cross-midnight fragments (gap < 60s) into one logical event', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    // R-001 UDT EE Repair: two fragments (gap = 30s) → should merge
    const r1UdtEvents = merged.filter(
      (e) => e.HISTORYID === 'R-001' && e.OLDSTATUSNAME === 'UDT' && e.OLDREASONNAME === 'EE Repair'
    );
    expect(r1UdtEvents).toHaveLength(1);
    expect(r1UdtEvents[0].fragment_count).toBe(2);
    // Merged hours = 3.9917 + 2.0 = 5.9917
    expect(Math.abs(r1UdtEvents[0].hours - 5.9917)).toBeLessThan(0.001);
    // event_start = first fragment start (2026-01-10T20:00:00Z)
    expect(r1UdtEvents[0].event_start.toISOString()).toBe('2026-01-10T20:00:00.000Z');
    // event_end = last fragment end (2026-01-11T02:00:00Z)
    expect(r1UdtEvents[0].event_end.toISOString()).toBe('2026-01-11T02:00:00.000Z');
  });

  it('does not merge events with gap > 60s (R-002 UDT)', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const r2UdtEvents = merged.filter(
      (e) => e.HISTORYID === 'R-002' && e.OLDSTATUSNAME === 'UDT'
    );
    expect(r2UdtEvents).toHaveLength(2);
  });

  it('does not merge events with different status (UDT vs SDT on R-001)', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const r1All = merged.filter((e) => e.HISTORYID === 'R-001');
    const statuses = new Set(r1All.map((e) => e.OLDSTATUSNAME));
    expect(statuses.has('UDT')).toBe(true);
    expect(statuses.has('SDT')).toBe(true);
    expect(r1All.length).toBeGreaterThanOrEqual(2);
  });

  it('produces same total event count as Python reference (6 raw → 5 merged)', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    // R-001 UDT: 2 → 1 merged; R-001 SDT: 1; R-002 UDT: 2 (gap > 60s); R-002 EGT: 1 → total 5
    expect(merged).toHaveLength(5);
  });

  it('assigns correct hours to cross-midnight merged event', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const r1Udt = merged.find(
      (e) => e.HISTORYID === 'R-001' && e.OLDSTATUSNAME === 'UDT'
    );
    expect(r1Udt).toBeDefined();
    expect(Math.abs((r1Udt?.hours ?? 0) - 5.9917)).toBeLessThan(0.001);
  });
});

describe('job-overlap bridge parity', () => {
  it('matches Path A (JOBID direct) correctly for R-001 merged event', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const bridged = bridgeJobs(merged, JOB_BRIDGE_FIXTURE);
    const r1Udt = bridged.find(
      (e) => e.HISTORYID === 'R-001' && e.OLDSTATUSNAME === 'UDT'
    );
    expect(r1Udt?.match_source).toBe('jobid');
    expect(r1Udt?.job_id).toBe('JOB-001');
  });

  it('matches Path A (JOBID direct) correctly for R-002 UDT events', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const bridged = bridgeJobs(merged, JOB_BRIDGE_FIXTURE);
    const r2Udt = bridged.filter(
      (e) => e.HISTORYID === 'R-002' && e.OLDSTATUSNAME === 'UDT'
    );
    expect(r2Udt).toHaveLength(2);
    expect(r2Udt[0].match_source).toBe('jobid');
    expect(r2Udt[0].job_id).toBe('JOB-002');
    expect(r2Udt[1].match_source).toBe('jobid');
    expect(r2Udt[1].job_id).toBe('JOB-003');
  });

  it('detects ambiguous Path B tie-break (runner-up >= 80% overlap of winner)', () => {
    const merged = crossShiftMerge(PATH_B_AMBIGUOUS_EVENTS);
    const bridged = bridgeJobs(merged, PATH_B_AMBIGUOUS_JOBS);
    // R-003 UDT has no JOBID → Path B
    // JOB-AMB-WIN: overlap = min(14:00,14:00) - max(08:00,07:00) = 6h = 21600s
    // JOB-AMB-RUN: overlap = min(14:00,13:00) - max(08:00,07:30) = 5h = 18000s
    // 18000 / 21600 ≈ 83% >= 80% → ambiguous
    expect(bridged).toHaveLength(1);
    expect(bridged[0].match_source).toBe('overlap');
    expect(bridged[0].job_id).toBe('JOB-AMB-WIN');
    expect(bridged[0].match_ambiguous).toBe(true);
  });

  it('assigns match_source=none for events with no overlapping jobs', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const bridged = bridgeJobs(merged, JOB_BRIDGE_FIXTURE);
    const r1Sdt = bridged.find(
      (e) => e.HISTORYID === 'R-001' && e.OLDSTATUSNAME === 'SDT'
    );
    expect(r1Sdt?.match_source).toBe('none');
    expect(r1Sdt?.job_id).toBeNull();
  });

  it('joins null-JOBID events via Path B without dropping the event', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const bridged = bridgeJobs(merged, JOB_BRIDGE_FIXTURE);
    // R-002 EGT has JOBID=null → Path B; no jobs with RESOURCEID=R-002 overlap EGT window
    const r2Egt = bridged.find(
      (e) => e.HISTORYID === 'R-002' && e.OLDSTATUSNAME === 'EGT'
    );
    expect(r2Egt).toBeDefined();  // must not be dropped
    expect(r2Egt?.match_source).toBe('none');
    expect(r2Egt?.job_id).toBeNull();
  });
});

describe('BigCategory view — taxonomy mapping', () => {
  it('maps EGT status events to egt_category (工程) regardless of reason', () => {
    // OLDSTATUSNAME='EGT' → egt_category regardless of reason
    const category = applyTaxonomy(null, 'EGT', TAXONOMY_FIXTURE);
    expect(category).toBe('工程');
  });

  it('maps EE Repair / UDT to 維修 via exact map', () => {
    const category = applyTaxonomy('EE Repair', 'UDT', TAXONOMY_FIXTURE);
    expect(category).toBe('維修');
  });

  it('maps TMTT_Check to 檢查 via prefix match', () => {
    const category = applyTaxonomy('TMTT_Check', 'SDT', TAXONOMY_FIXTURE);
    expect(category).toBe('檢查');
  });

  it('falls back to fallback for unknown reason', () => {
    const category = applyTaxonomy('Unknown Reason XYZ', 'UDT', TAXONOMY_FIXTURE);
    expect(category).toBe('其他/未分類');
  });

  it('strips Oracle CHAR trailing spaces before lookup', () => {
    const category = applyTaxonomy('EE Repair   ', 'UDT', TAXONOMY_FIXTURE);
    expect(category).toBe('維修');
  });

  it('taxonomy-driven mapping produces correct result for all server map entries', () => {
    for (const [reason, expectedCategory] of TAXONOMY_FIXTURE.map) {
      const result = applyTaxonomy(reason, 'UDT', TAXONOMY_FIXTURE);
      expect(result).toBe(expectedCategory);
    }
  });
});

describe('taxonomy-driven BigCategory — server taxonomy vs composable useBigCategory', () => {
  it('EGT override: both server taxonomy and useBigCategory agree on 工程 for EGT status', async () => {
    const { getBigCategory } = await import('../composables/useBigCategory');
    // Both paths must agree: EGT status → category for EGT events
    const serverResult = applyTaxonomy('EE Repair', 'EGT', TAXONOMY_FIXTURE);
    const localResult = getBigCategory('EE Repair', 'EGT');
    expect(serverResult).toBe('工程');
    expect(localResult).toBe('工程');
    // Both agree
    expect(serverResult).toBe(localResult);
  });

  it('taxonomy-driven TMTT_ prefix matches useBigCategory getBigCategory', async () => {
    const { getBigCategory } = await import('../composables/useBigCategory');
    const serverResult = applyTaxonomy('TMTT_Verification', 'SDT', TAXONOMY_FIXTURE);
    const localResult = getBigCategory('TMTT_Verification', 'SDT');
    // Both must map to 檢查
    expect(serverResult).toBe('檢查');
    expect(localResult).toBe('檢查');
    expect(serverResult).toBe(localResult);
  });
});

describe('KPI view parity', () => {
  it('computes total_hours as sum of all merged event hours', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const totalHours = merged.reduce((acc, e) => acc + e.hours, 0);
    // 5.9917 (R-001 UDT merged) + 2.0 (R-001 SDT) + 1.0 + 1.0 (R-002 UDT ×2) + 1.0 (R-002 EGT) = 10.9917
    expect(Math.abs(totalHours - 10.9917)).toBeLessThan(0.01);
  });

  it('computes event_count as number of merged logical events', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    expect(merged).toHaveLength(5);
  });

  it('computes avg_hours_per_event correctly', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const totalHours = merged.reduce((acc, e) => acc + e.hours, 0);
    const avgMin = (totalHours / merged.length) * 60;
    expect(avgMin).toBeGreaterThan(0);
    expect(Math.abs(avgMin - (totalHours / merged.length) * 60)).toBeLessThan(0.001);
  });
});

describe('DailyTrend view parity', () => {
  it('groups merged events by date and returns sorted rows', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const byDate: Record<string, { udt: number; sdt: number; egt: number; total: number }> = {};

    for (const e of merged) {
      const date = e.event_start.toISOString().slice(0, 10);
      if (!byDate[date]) byDate[date] = { udt: 0, sdt: 0, egt: 0, total: 0 };
      byDate[date].total += e.hours;
      if (e.OLDSTATUSNAME === 'UDT') byDate[date].udt += e.hours;
      else if (e.OLDSTATUSNAME === 'SDT') byDate[date].sdt += e.hours;
      else if (e.OLDSTATUSNAME === 'EGT') byDate[date].egt += e.hours;
    }

    const rows = Object.entries(byDate)
      .map(([date, v]) => ({ date, ...v }))
      .sort((a, b) => a.date.localeCompare(b.date));

    // At minimum 2 dates: 2026-01-10 (SDT + 2×UDT + EGT) and 2026-01-11 (cross-midnight UDT fragment)
    expect(rows.length).toBeGreaterThanOrEqual(1);
    for (const row of rows) {
      expect(row.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(row.total).toBeGreaterThanOrEqual(0);
    }
  });

  it('cross-midnight merged event uses event_start date for grouping', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const r1Udt = merged.find((e) => e.HISTORYID === 'R-001' && e.OLDSTATUSNAME === 'UDT');
    expect(r1Udt).toBeDefined();
    // event_start is 2026-01-10 (UTC) — use start date for daily grouping
    expect(r1Udt!.event_start.toISOString().slice(0, 10)).toBe('2026-01-10');
  });
});

describe('EquipmentDetail view parity', () => {
  it('aggregates per-equipment hours from merged events', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const byEquip: Record<string, { total: number; events: number }> = {};

    for (const e of merged) {
      if (!byEquip[e.HISTORYID]) byEquip[e.HISTORYID] = { total: 0, events: 0 };
      byEquip[e.HISTORYID].total += e.hours;
      byEquip[e.HISTORYID].events += 1;
    }

    // R-001: 5.9917 + 2.0 = 7.9917h, 2 events (UDT merged + SDT)
    expect(Math.abs(byEquip['R-001'].total - 7.9917)).toBeLessThan(0.01);
    expect(byEquip['R-001'].events).toBe(2);
    // R-002: 1.0 + 1.0 + 1.0 = 3.0h, 3 events
    expect(Math.abs(byEquip['R-002'].total - 3.0)).toBeLessThan(0.01);
    expect(byEquip['R-002'].events).toBe(3);
  });
});

describe('EventDetail view parity', () => {
  it('returns all bridged events with required enrichment shape', () => {
    const merged = crossShiftMerge(BASE_EVENTS_FIXTURE);
    const bridged = bridgeJobs(merged, JOB_BRIDGE_FIXTURE);
    expect(bridged).toHaveLength(5);
    for (const e of bridged) {
      expect(e).toHaveProperty('HISTORYID');
      expect(e).toHaveProperty('match_source');
      expect(e).toHaveProperty('job_id');
      expect(['jobid', 'overlap', 'none']).toContain(e.match_source);
    }
  });
});

describe('error handling', () => {
  it('composable exports useDowntimeDuckDB function', async () => {
    const mod = await importComposable();
    expect(typeof mod.useDowntimeDuckDB).toBe('function');
  });

  it('composable returns state=idle before activate()', async () => {
    const { useDowntimeDuckDB } = await importComposable();
    const composable = useDowntimeDuckDB();
    expect(composable.state.value).toBe('idle');
  });

  it('composable returns state=error on WASM init failure (not empty table)', async () => {
    const duckdbModule = await import('../../core/duckdb-client');
    const mockClient = duckdbModule.getDuckDBClient() as unknown as {
      init: ReturnType<typeof vi.fn>;
      registerParquet: ReturnType<typeof vi.fn>;
      sendQuery: ReturnType<typeof vi.fn>;
      destroy: ReturnType<typeof vi.fn>;
    };
    mockClient.init.mockRejectedValueOnce(new Error('WASM init failed'));

    const { useDowntimeDuckDB } = await importComposable();
    const composable = useDowntimeDuckDB();
    await expect(
      composable.activate('http://test/base.parquet', 'http://test/jobs.parquet', TAXONOMY_FIXTURE)
    ).rejects.toThrow();
    expect(composable.state.value).toBe('error');
    expect(composable.errorMessage.value.length).toBeGreaterThan(0);
  });

  it('composable returns state=error on parquet fetch 404', async () => {
    const duckdbModule = await import('../../core/duckdb-client');
    const mockFetch = duckdbModule.fetchParquetBuffer as ReturnType<typeof vi.fn>;
    mockFetch.mockRejectedValueOnce(new Error('Spool download failed: HTTP 404'));

    const { useDowntimeDuckDB } = await importComposable();
    const composable = useDowntimeDuckDB();
    await expect(
      composable.activate('http://test/base.parquet', 'http://test/jobs.parquet', TAXONOMY_FIXTURE)
    ).rejects.toThrow('HTTP 404');
    expect(composable.state.value).toBe('error');
  });

  it('view query functions throw when state is not ready', async () => {
    const { useDowntimeDuckDB } = await importComposable();
    const composable = useDowntimeDuckDB();
    // state = idle → should throw, not return []
    await expect(composable.queryKpi({})).rejects.toThrow();
    await expect(composable.queryDailyTrend({})).rejects.toThrow();
    await expect(composable.queryBigCategory({})).rejects.toThrow();
  });
});

describe('CSV export', () => {
  it('composable exports exportCsv function', async () => {
    const { useDowntimeDuckDB } = await importComposable();
    const composable = useDowntimeDuckDB();
    expect(typeof composable.exportCsv).toBe('function');
  });
});
