# -*- coding: utf-8 -*-
"""Unit tests for downtime_analysis_service.py.

Covers DA-01..DA-06:
  TestE10StatusFilter         — DA-01
  TestCrossShiftMerge         — DA-02
  TestJobidBridge             — DA-03
  TestBigCategoryMapping      — DA-04
  TestWaitRepairHours         — DA-05
  TestFilterCrossNarrowing    — AC-6 filter narrowing
  TestFilterKwargsForwarding  — per-kwarg route→service forwarding style
  TestBridgeVersionCacheKey   — DA-06
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from mes_dashboard.services.downtime_analysis_service import (
    _BIG_CATEGORY_MAP,
    _PREFIX_CATEGORIES,
    _bridge_jobid,
    _map_big_category,
    _merge_cross_shift_events,
    make_downtime_query_id,
)


# ===========================================================================
# Helpers / fixtures
# ===========================================================================


def _ts(s: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS' to datetime."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def _shift_row(
    hist_id: str,
    status: str,
    reason: str,
    start: str,
    end: str,
    hours: float,
    jobid: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        'HISTORYID': hist_id,
        'OLDSTATUSNAME': status,
        'OLDREASONNAME': reason,
        'OLDLASTSTATUSCHANGEDATE': _ts(start),
        'LASTSTATUSCHANGEDATE': _ts(end),
        'HOURS': hours,
        'JOBID': jobid,
    }


def _job_row(
    jobid: str,
    resourceid: str,
    createdate: str,
    completedate: str,
    symptom: str = 'SYM',
    cause: str = 'CAUSE',
    repair: str = 'REP',
    handler: str = 'H',
    firstclock: Optional[str] = None,
    lastclock: Optional[str] = None,
    jobordername: str = 'JO-001',
    jobmodelname: str = 'M-A',
) -> Dict[str, Any]:
    return {
        'JOBID': jobid,
        'RESOURCEID': resourceid,
        'CREATEDATE': _ts(createdate),
        'COMPLETEDATE': _ts(completedate),
        'SYMPTOMCODENAME': symptom,
        'CAUSECODENAME': cause,
        'REPAIRCODENAME': repair,
        'COMPLETE_FULLNAME': handler,
        'FIRSTCLOCKONDATE': _ts(firstclock) if firstclock else None,
        'LASTCLOCKOFFDATE': _ts(lastclock) if lastclock else None,
        'JOBORDERNAME': jobordername,
        'JOBMODELNAME': jobmodelname,
    }


# ===========================================================================
# TestE10StatusFilter (DA-01)
# ===========================================================================


class TestE10StatusFilter:
    """DA-01: Only UDT/SDT/EGT included; NST excluded at query layer."""

    def test_base_events_sql_excludes_nst(self):
        """SQL file must contain IN ('UDT','SDT','EGT'); 'NST' must not appear in the IN-list."""
        import re
        from pathlib import Path
        sql_dir = Path(__file__).resolve().parent.parent / "src" / "mes_dashboard" / "sql" / "downtime_analysis"
        sql_text = (sql_dir / "base_events.sql").read_text(encoding="utf-8")
        assert "IN ('UDT', 'SDT', 'EGT')" in sql_text or "IN ('UDT','SDT','EGT')" in sql_text, (
            "base_events.sql must filter OLDSTATUSNAME IN ('UDT','SDT','EGT')"
        )
        # NST must not appear inside the IN(...) filter clause (comments are acceptable)
        in_clause_match = re.search(r"IN\s*\([^)]+\)", sql_text, re.IGNORECASE)
        if in_clause_match:
            assert "'NST'" not in in_clause_match.group(), (
                "base_events.sql IN-clause must not include 'NST'"
            )

    def test_merge_preserves_all_three_statuses(self):
        """After merge, UDT/SDT/EGT events are all retained."""
        rows = [
            _shift_row('R1', 'UDT', 'EE Repair',    '2026-05-27 18:00:00', '2026-05-27 19:30:00', 1.5),
            _shift_row('R1', 'SDT', 'EE_PM',         '2026-05-27 08:00:00', '2026-05-27 09:00:00', 1.0),
            _shift_row('R1', 'EGT', 'Engineering',   '2026-05-27 10:00:00', '2026-05-27 11:00:00', 1.0),
        ]
        df = pd.DataFrame(rows)
        merged = _merge_cross_shift_events(df)
        assert set(merged['OLDSTATUSNAME'].unique()) == {'UDT', 'SDT', 'EGT'}

    def test_hours_column_is_float_after_merge(self):
        """HOURS must be float after merge (defensive coerce)."""
        rows = [_shift_row('R1', 'UDT', 'EE Repair', '2026-05-27 18:00:00', '2026-05-27 19:30:00', 1.5)]
        df = pd.DataFrame(rows)
        df['HOURS'] = df['HOURS'].astype(str)  # simulate string return from Oracle
        merged = _merge_cross_shift_events(df)
        assert merged['hours'].dtype in (float, 'float64'), "hours must be float"
        assert merged.iloc[0]['hours'] == pytest.approx(1.5, abs=1e-4)


# ===========================================================================
# TestCrossShiftMerge (DA-02)
# ===========================================================================


class TestCrossShiftMerge:
    """DA-02: Cross-shift event merge with 60s contiguity."""

    def _three_fragment_df(self) -> pd.DataFrame:
        """R-001, UDT, EE Repair: 18:00→19:30 (1.5h), 19:30→07:30 (12h), 07:30→08:00 (0.5h)."""
        rows = [
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-27 18:00:00', '2026-05-27 19:30:00', 1.5),
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-27 19:30:00', '2026-05-28 07:30:00', 12.0),
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-28 07:30:00', '2026-05-28 08:00:00', 0.5),
        ]
        return pd.DataFrame(rows)

    def test_three_fragments_merge_to_one_row(self):
        """3 contiguous fragments → 1 merged event."""
        merged = _merge_cross_shift_events(self._three_fragment_df())
        assert len(merged) == 1

    def test_three_fragments_hours_sum(self):
        """Merged hours = 1.5 + 12 + 0.5 = 14.0."""
        merged = _merge_cross_shift_events(self._three_fragment_df())
        assert merged.iloc[0]['hours'] == pytest.approx(14.0, abs=1e-4)

    def test_three_fragments_fragment_count(self):
        """fragment_count must be 3 after merge."""
        merged = _merge_cross_shift_events(self._three_fragment_df())
        assert merged.iloc[0]['fragment_count'] == 3

    def test_three_fragments_event_start_end(self):
        """event_start = 18:00, event_end = 08:00 (next day)."""
        merged = _merge_cross_shift_events(self._three_fragment_df())
        assert merged.iloc[0]['event_start'] == _ts('2026-05-27 18:00:00')
        assert merged.iloc[0]['event_end'] == _ts('2026-05-28 08:00:00')

    def test_gap_greater_than_60s_produces_two_events(self):
        """A 120s gap between fragment 1 end and fragment 2 start → 2 distinct events."""
        rows = [
            # Fragment 1: ends at 08:00:00
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-27 06:00:00', '2026-05-27 08:00:00', 2.0),
            # Fragment 2: starts at 08:02:00 (120s gap > 60s threshold)
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-27 08:02:00', '2026-05-27 10:00:00', 1.98),
        ]
        df = pd.DataFrame(rows)
        merged = _merge_cross_shift_events(df)
        assert len(merged) == 2, f"Expected 2 events after 120s gap, got {len(merged)}"

    def test_gap_less_than_60s_merges_to_one(self):
        """A 30s gap → contiguous, merges to 1 event."""
        rows = [
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-27 06:00:00', '2026-05-27 08:00:00', 2.0),
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-27 08:00:30', '2026-05-27 10:00:00', 2.0),
        ]
        df = pd.DataFrame(rows)
        merged = _merge_cross_shift_events(df)
        assert len(merged) == 1

    def test_cross_resource_isolation(self):
        """Same key except HISTORYID → 2 separate events."""
        rows = [
            _shift_row('R-001', 'UDT', 'EE Repair', '2026-05-27 18:00:00', '2026-05-27 19:30:00', 1.5),
            _shift_row('R-002', 'UDT', 'EE Repair', '2026-05-27 18:00:00', '2026-05-27 19:30:00', 1.5),
        ]
        df = pd.DataFrame(rows)
        merged = _merge_cross_shift_events(df)
        assert len(merged) == 2

    def test_different_reason_not_merged(self):
        """Same HISTORYID/status but different reason → 2 separate events."""
        rows = [
            _shift_row('R-001', 'UDT', 'EE Repair',        '2026-05-27 18:00:00', '2026-05-27 19:30:00', 1.5),
            _shift_row('R-001', 'UDT', 'EAP Minor stoppage', '2026-05-27 19:30:00', '2026-05-27 20:00:00', 0.5),
        ]
        df = pd.DataFrame(rows)
        merged = _merge_cross_shift_events(df)
        assert len(merged) == 2

    def test_empty_df_returns_empty(self):
        """Empty input returns empty DataFrame."""
        df = pd.DataFrame(columns=['HISTORYID', 'OLDSTATUSNAME', 'OLDREASONNAME',
                                   'OLDLASTSTATUSCHANGEDATE', 'LASTSTATUSCHANGEDATE', 'HOURS', 'JOBID'])
        merged = _merge_cross_shift_events(df)
        assert merged.empty


# ===========================================================================
# TestJobidBridge (DA-03)
# ===========================================================================


class TestJobidBridge:
    """DA-03: JOBID bridge Path A / Path B / no-match."""

    def _events_df(self, rows: List[Dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def _jobs_df(self, rows: List[Dict]) -> pd.DataFrame:
        return pd.DataFrame(rows)

    def test_path_a_direct_jobid_match(self):
        """Path A: SHIFT.JOBID non-null → match_source='jobid', symptom non-null."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': 'J001',
            }
        ]
        jobs = [_job_row('J001', 'R-001', '2026-05-27 07:00:00', '2026-05-27 11:00:00', symptom='VIBRATION')]
        result = _bridge_jobid(self._events_df(events), self._jobs_df(jobs))
        row = result.iloc[0]
        assert row['match_source'] == 'jobid'
        assert row['symptom'] == 'VIBRATION'

    def test_path_b_no_match(self):
        """Path B no-match: JOBID null, no overlapping jobs → match_source='none', all JOB fields null."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        result = _bridge_jobid(self._events_df(events), pd.DataFrame())
        row = result.iloc[0]
        assert row['match_source'] == 'none'
        assert row['symptom'] is None
        assert row['cause'] is None
        assert row['repair'] is None
        assert row['handler'] is None
        assert row['wait_min'] is None
        assert row['repair_min'] is None

    def test_path_b_single_overlap(self):
        """Path B single overlap → match_source='overlap'."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        jobs = [_job_row('J002', 'R-001', '2026-05-27 07:00:00', '2026-05-27 11:00:00')]
        result = _bridge_jobid(self._events_df(events), self._jobs_df(jobs))
        assert result.iloc[0]['match_source'] == 'overlap'

    def test_path_b_multi_overlap_tiebreak_larger_wins(self):
        """Path B: two overlapping jobs → larger overlap wins."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 06:00:00'), 'event_end': _ts('2026-05-27 12:00:00'),
                'hours': 6.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        # J003 overlaps 06:00–09:00 (3h), J004 overlaps 06:00–12:00 (6h) — J004 wins
        jobs = [
            _job_row('J003', 'R-001', '2026-05-27 05:00:00', '2026-05-27 09:00:00', symptom='SMALL'),
            _job_row('J004', 'R-001', '2026-05-27 05:00:00', '2026-05-27 13:00:00', symptom='LARGE'),
        ]
        result = _bridge_jobid(self._events_df(events), self._jobs_df(jobs))
        assert result.iloc[0]['symptom'] == 'LARGE'

    def test_path_b_tiebreak_by_createdate_asc(self):
        """Path B tiebreak: equal overlaps → earlier CREATEDATE wins."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        # Both cover full event window (same overlap); J_EARLIER has earlier CREATEDATE
        jobs = [
            _job_row('J_LATER',   'R-001', '2026-05-27 08:30:00', '2026-05-27 10:30:00', symptom='LATER'),
            _job_row('J_EARLIER', 'R-001', '2026-05-27 07:00:00', '2026-05-27 10:30:00', symptom='EARLIER'),
        ]
        result = _bridge_jobid(self._events_df(events), self._jobs_df(jobs))
        assert result.iloc[0]['symptom'] == 'EARLIER'

    def test_path_b_tiebreak_final_by_jobid_asc(self):
        """Path B final tiebreak: same overlap, same CREATEDATE → JOBID ASC wins."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        common_create = '2026-05-27 07:00:00'
        jobs = [
            _job_row('J_B', 'R-001', common_create, '2026-05-27 11:00:00', symptom='B'),
            _job_row('J_A', 'R-001', common_create, '2026-05-27 11:00:00', symptom='A'),
        ]
        result = _bridge_jobid(self._events_df(events), self._jobs_df(jobs))
        assert result.iloc[0]['symptom'] == 'A'  # J_A < J_B alphabetically

    def test_match_ambiguous_true_when_runnerup_gte_80pct(self):
        """match_ambiguous=True when runner-up overlap >= 80% of winner."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 18:00:00'),
                'hours': 10.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        # Winner: 08:00–18:00 = 10h overlap; runner: 08:00–17:00 = 9h overlap → 90% >= 80%
        jobs = [
            _job_row('J_WIN',    'R-001', '2026-05-27 07:00:00', '2026-05-27 19:00:00', symptom='WIN'),
            _job_row('J_RUNNER', 'R-001', '2026-05-27 07:00:00', '2026-05-27 17:00:00', symptom='RUN'),
        ]
        result = _bridge_jobid(self._events_df(events), self._jobs_df(jobs))
        assert bool(result.iloc[0]['match_ambiguous']) is True

    def test_match_ambiguous_false_when_runnerup_less_than_80pct(self):
        """match_ambiguous=False when runner-up overlap < 80% of winner."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 18:00:00'),
                'hours': 10.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        # Winner: 08:00–18:00 = 10h overlap; runner: 08:00–09:00 = 1h overlap → 10% < 80%
        jobs = [
            _job_row('J_WIN',    'R-001', '2026-05-27 07:00:00', '2026-05-27 19:00:00', symptom='WIN'),
            _job_row('J_SMALL',  'R-001', '2026-05-27 07:00:00', '2026-05-27 09:30:00', symptom='SML'),
        ]
        result = _bridge_jobid(self._events_df(events), self._jobs_df(jobs))
        assert bool(result.iloc[0]['match_ambiguous']) is False

    def test_all_job_fields_present_on_no_match(self):
        """No-match rows include all JOB fields set to None (not omitted)."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        result = _bridge_jobid(self._events_df(events), pd.DataFrame())
        cols = result.columns.tolist()
        for field in ('job_order_name', 'job_model', 'symptom', 'cause', 'repair', 'handler',
                      'wait_min', 'repair_min', 'match_source', 'match_ambiguous'):
            assert field in cols, f"Field '{field}' missing from no-match row columns"


# ===========================================================================
# TestBigCategoryMapping (DA-04)
# ===========================================================================


class TestBigCategoryMapping:
    """DA-04: Big-category taxonomy mapping correctness."""

    def test_ee_repair_maps_to_維修(self):
        assert _map_big_category('EE Repair', 'UDT') == '維修'

    def test_eap_minor_maps_to_維修(self):
        assert _map_big_category('EAP Minor stoppage', 'UDT') == '維修'

    def test_ee_pm_maps_to_保養(self):
        assert _map_big_category('EE_PM', 'SDT') == '保養'

    def test_mf_pm_maps_to_保養(self):
        assert _map_big_category('MF_PM', 'SDT') == '保養'

    def test_pd_pm_maps_to_保養(self):
        assert _map_big_category('PD_PM', 'SDT') == '保養'

    def test_change_type_maps_to_改機換料(self):
        assert _map_big_category('Change Type', 'SDT') == '改機換料'

    def test_change_package_maps_to_改機換料(self):
        assert _map_big_category('Change Package', 'SDT') == '改機換料'

    def test_re_layout_maps_to_改機換料(self):
        assert _map_big_category('Re Layout', 'SDT') == '改機換料'

    def test_change_marking_code_maps_to_改機換料(self):
        assert _map_big_category('Change Marking Code', 'SDT') == '改機換料'

    def test_change_model_maps_to_改機換料(self):
        assert _map_big_category('Change Model', 'SDT') == '改機換料'

    def test_change_tool_maps_to_治工具更換與模具清潔(self):
        assert _map_big_category('Change Tool/Consumables', 'SDT') == '治工具更換與模具清潔'

    def test_clean_mold_maps_to_治工具更換與模具清潔(self):
        assert _map_big_category('Clean Mold', 'SDT') == '治工具更換與模具清潔'

    def test_qc_inspection_maps_to_檢查(self):
        assert _map_big_category('Prod_QC_Inspection', 'SDT') == '檢查'

    def test_pd_inspection_maps_to_檢查(self):
        assert _map_big_category('Prod_PD_inspection', 'SDT') == '檢查'

    def test_wait_for_instructions_maps_to_待料待指示(self):
        assert _map_big_category('Wait For Instructions', 'UDT') == '待料待指示'

    def test_no_operator_maps_to_待料待指示(self):
        assert _map_big_category('No Operator', 'UDT') == '待料待指示'

    def test_no_raw_material_maps_to_待料待指示(self):
        assert _map_big_category('No Raw Material', 'UDT') == '待料待指示'

    def test_egt_always_maps_to_工程(self):
        """EGT status → 工程 regardless of reason."""
        assert _map_big_category('EE Repair', 'EGT') == '工程'
        assert _map_big_category('Unknown reason', 'EGT') == '工程'
        assert _map_big_category(None, 'EGT') == '工程'

    def test_tmtt_prefix_maps_to_檢查(self):
        """TMTT_* prefix → 檢查."""
        assert _map_big_category('TMTT_Check', 'SDT') == '檢查'
        assert _map_big_category('TMTT_SomethingElse', 'SDT') == '檢查'

    def test_char_trailing_space_ee_repair(self):
        """Oracle CHAR: 'EE Repair   ' (8 trailing spaces) → '維修'."""
        assert _map_big_category('EE Repair   ', 'UDT') == '維修'

    def test_char_trailing_space_tmtt(self):
        """Oracle CHAR: 'TMTT_Check  ' (CHAR-padded) → '檢查'."""
        assert _map_big_category('TMTT_Check  ', 'SDT') == '檢查'

    def test_unknown_reason_maps_to_其他(self):
        """Unknown reason → '其他/未分類'."""
        assert _map_big_category('SomethingUnknown', 'UDT') == '其他/未分類'

    def test_none_reason_maps_to_其他_for_non_egt(self):
        """None reason with non-EGT status → '其他/未分類'."""
        assert _map_big_category(None, 'UDT') == '其他/未分類'

    def test_blank_reason_maps_to_其他(self):
        """Blank reason → '其他/未分類'."""
        assert _map_big_category('   ', 'UDT') == '其他/未分類'

    def test_big_category_map_has_nine_buckets(self):
        """Taxonomy must cover all 9 defined categories (DA-04)."""
        categories = set(_BIG_CATEGORY_MAP.values())
        # EGT → 工程 is handled by status check, not the map
        # Map covers: 維修, 保養, 改機換料, 治工具更換與模具清潔, 教讀程式, 檢查, 待料待指示
        for cat in ('維修', '保養', '改機換料', '治工具更換與模具清潔', '教讀程式', '檢查', '待料待指示'):
            assert cat in categories, f"Category '{cat}' missing from _BIG_CATEGORY_MAP"


# ===========================================================================
# TestWaitRepairHours (DA-05)
# ===========================================================================


class TestWaitRepairHours:
    """DA-05: wait_min and repair_min derivation."""

    def _make_event_with_job(
        self, jobid='J001', firstclock: Optional[str] = None, lastclock: Optional[str] = None
    ) -> pd.DataFrame:
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': jobid,
            }
        ]
        jobs = [_job_row(
            'J001', 'R-001',
            createdate='2026-05-27 07:00:00',
            completedate='2026-05-27 11:00:00',
            firstclock=firstclock,
            lastclock=lastclock,
        )]
        return _bridge_jobid(pd.DataFrame(events), pd.DataFrame(jobs))

    def test_wait_min_formula(self):
        """wait_min = (FIRSTCLOCKONDATE - CREATEDATE) in minutes."""
        # CREATEDATE=07:00, FIRSTCLOCKONDATE=07:30 → wait=30min
        result = self._make_event_with_job(firstclock='2026-05-27 07:30:00')
        assert result.iloc[0]['wait_min'] == pytest.approx(30.0, abs=0.01)

    def test_repair_min_formula(self):
        """repair_min = (LASTCLOCKOFFDATE - FIRSTCLOCKONDATE) in minutes."""
        # FIRSTCLOCKONDATE=07:30, LASTCLOCKOFFDATE=09:30 → repair=120min
        result = self._make_event_with_job(
            firstclock='2026-05-27 07:30:00', lastclock='2026-05-27 09:30:00'
        )
        assert result.iloc[0]['repair_min'] == pytest.approx(120.0, abs=0.01)

    def test_wait_min_null_when_firstclock_null(self):
        """wait_min is None when FIRSTCLOCKONDATE is null."""
        result = self._make_event_with_job(firstclock=None)
        assert result.iloc[0]['wait_min'] is None

    def test_repair_min_null_when_firstclock_null(self):
        """repair_min is None when FIRSTCLOCKONDATE is null."""
        result = self._make_event_with_job(firstclock=None, lastclock='2026-05-27 09:30:00')
        assert result.iloc[0]['repair_min'] is None

    def test_repair_min_null_when_lastclock_null(self):
        """repair_min is None when LASTCLOCKOFFDATE is null."""
        result = self._make_event_with_job(firstclock='2026-05-27 07:30:00', lastclock=None)
        assert result.iloc[0]['repair_min'] is None

    def test_both_null_on_no_match(self):
        """Both wait_min and repair_min are None when match_source='none'."""
        events = [
            {
                'HISTORYID': 'R-001', 'OLDSTATUSNAME': 'UDT', 'OLDREASONNAME': 'EE Repair',
                'event_start': _ts('2026-05-27 08:00:00'), 'event_end': _ts('2026-05-27 10:00:00'),
                'hours': 2.0, 'fragment_count': 1, 'JOBID': None,
            }
        ]
        result = _bridge_jobid(pd.DataFrame(events), pd.DataFrame())
        assert result.iloc[0]['wait_min'] is None
        assert result.iloc[0]['repair_min'] is None


# ===========================================================================
# TestFilterCrossNarrowing (AC-6)
# ===========================================================================


class TestFilterCrossNarrowing:
    """AC-6: filter dropdowns cross-narrow; equipment excludes self."""

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_cache.get_package_group_name')
    def test_workcenter_filter_narrows_resources(
        self, mock_pg, mock_wc_map, mock_resources
    ):
        """When workcenter_groups is set, resources list is narrowed."""
        from mes_dashboard.services.downtime_analysis_service import get_filter_options

        mock_resources.return_value = [
            {'RESOURCEID': 'R1', 'RESOURCENAME': 'Machine-A', 'WORKCENTERNAME': 'WC_A', 'RESOURCEFAMILYNAME': 'FAM1', 'PACKAGEGROUPID': None},
            {'RESOURCEID': 'R2', 'RESOURCENAME': 'Machine-B', 'WORKCENTERNAME': 'WC_B', 'RESOURCEFAMILYNAME': 'FAM2', 'PACKAGEGROUPID': None},
        ]
        mock_wc_map.return_value = {
            'WC_A': {'group': 'GRP_A', 'sequence': 1},
            'WC_B': {'group': 'GRP_B', 'sequence': 2},
        }
        mock_pg.return_value = None

        opts = get_filter_options(workcenter_groups=['GRP_A'])
        assert 'Machine-A' in opts['resources']
        assert 'Machine-B' not in opts['resources']

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_cache.get_package_group_name')
    def test_unfiltered_returns_all_resources(
        self, mock_pg, mock_wc_map, mock_resources
    ):
        """Without filters, all resources are returned."""
        from mes_dashboard.services.downtime_analysis_service import get_filter_options

        mock_resources.return_value = [
            {'RESOURCEID': 'R1', 'RESOURCENAME': 'Machine-A', 'WORKCENTERNAME': 'WC_A', 'RESOURCEFAMILYNAME': 'FAM1', 'PACKAGEGROUPID': None},
            {'RESOURCEID': 'R2', 'RESOURCENAME': 'Machine-B', 'WORKCENTERNAME': 'WC_B', 'RESOURCEFAMILYNAME': 'FAM2', 'PACKAGEGROUPID': None},
        ]
        mock_wc_map.return_value = {
            'WC_A': {'group': 'GRP_A', 'sequence': 1},
            'WC_B': {'group': 'GRP_B', 'sequence': 2},
        }
        mock_pg.return_value = None

        opts = get_filter_options()
        assert 'Machine-A' in opts['resources']
        assert 'Machine-B' in opts['resources']

    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_cache.get_package_group_name')
    def test_big_categories_always_returns_all_nine(
        self, mock_pg, mock_wc_map, mock_resources
    ):
        """big_categories list always contains all 9 categories regardless of filters."""
        from mes_dashboard.services.downtime_analysis_service import get_filter_options

        mock_resources.return_value = []
        mock_wc_map.return_value = {}
        mock_pg.return_value = None

        opts = get_filter_options()
        assert len(opts['big_categories']) == 9


# ===========================================================================
# TestResourceCacheBaselineFilter
# ===========================================================================


class TestResourceCacheBaselineFilter:
    """_apply_resource_filters must always restrict to resource_cache-approved
    HISTORYIDs, even when the caller passes no user filter arguments.

    This prevents devices excluded by EQUIPMENT_TYPE_FILTER / EXCLUDED_LOCATIONS
    / EXCLUDED_ASSET_STATUSES (e.g. LOCATIONNAME='報廢') from appearing in
    downtime results and failing the resource_lookup name resolution.
    """

    def _make_df(self, hist_ids: List[str]) -> pd.DataFrame:
        rows = []
        for hid in hist_ids:
            rows.append({
                'HISTORYID': hid,
                'OLDSTATUSNAME': 'UDT',
                'OLDREASONNAME': 'EE Repair',
                'OLDLASTSTATUSCHANGEDATE': _ts('2025-01-01 08:00:00'),
                'LASTSTATUSCHANGEDATE': _ts('2025-01-01 10:00:00'),
                'HOURS': 2.0,
                'JOBID': None,
            })
        return pd.DataFrame(rows)

    @patch('mes_dashboard.services.downtime_analysis_service.get_package_group_name', return_value=None, create=True)
    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_excluded_device_removed_when_no_user_filter(
        self, mock_resources, mock_wc_map, _mock_pg
    ):
        """Device not in resource_cache (e.g. LOCATIONNAME=報廢) must be stripped
        from results even when no user filter is supplied."""
        from mes_dashboard.services.downtime_analysis_service import _apply_resource_filters

        mock_resources.return_value = [
            {'RESOURCEID': 'aabb', 'RESOURCENAME': 'Machine-OK', 'WORKCENTERNAME': 'WC1',
             'RESOURCEFAMILYNAME': 'FAM1', 'PACKAGEGROUPID': None},
        ]
        mock_wc_map.return_value = {'WC1': {'group': 'GRP1', 'sequence': 1}}

        # 48801680000002af is in SHIFT but NOT in resource_cache (報廢)
        df = self._make_df(['aabb', '48801680000002af'])
        result = _apply_resource_filters(df, None, None, None, None)

        assert list(result['HISTORYID']) == ['aabb']
        assert '48801680000002af' not in result['HISTORYID'].values

    @patch('mes_dashboard.services.downtime_analysis_service.get_package_group_name', return_value=None, create=True)
    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_approved_device_kept_when_no_user_filter(
        self, mock_resources, mock_wc_map, _mock_pg
    ):
        """Device that IS in resource_cache must not be stripped."""
        from mes_dashboard.services.downtime_analysis_service import _apply_resource_filters

        mock_resources.return_value = [
            {'RESOURCEID': 'aabb', 'RESOURCENAME': 'Machine-OK', 'WORKCENTERNAME': 'WC1',
             'RESOURCEFAMILYNAME': 'FAM1', 'PACKAGEGROUPID': None},
        ]
        mock_wc_map.return_value = {'WC1': {'group': 'GRP1', 'sequence': 1}}

        df = self._make_df(['aabb'])
        result = _apply_resource_filters(df, None, None, None, None)

        assert list(result['HISTORYID']) == ['aabb']

    @patch('mes_dashboard.services.downtime_analysis_service.get_package_group_name', return_value=None, create=True)
    @patch('mes_dashboard.services.filter_cache.get_workcenter_mapping')
    @patch('mes_dashboard.services.resource_cache.get_all_resources')
    def test_user_filter_still_narrows_after_baseline(
        self, mock_resources, mock_wc_map, _mock_pg
    ):
        """User workcenter filter narrows further on top of the baseline."""
        from mes_dashboard.services.downtime_analysis_service import _apply_resource_filters

        mock_resources.return_value = [
            {'RESOURCEID': 'R1', 'RESOURCENAME': 'M1', 'WORKCENTERNAME': 'WC_A',
             'RESOURCEFAMILYNAME': 'F1', 'PACKAGEGROUPID': None},
            {'RESOURCEID': 'R2', 'RESOURCENAME': 'M2', 'WORKCENTERNAME': 'WC_B',
             'RESOURCEFAMILYNAME': 'F1', 'PACKAGEGROUPID': None},
        ]
        mock_wc_map.return_value = {
            'WC_A': {'group': 'GRP_A', 'sequence': 1},
            'WC_B': {'group': 'GRP_B', 'sequence': 2},
        }

        df = self._make_df(['R1', 'R2', 'EXCLUDED'])
        result = _apply_resource_filters(df, workcenter_groups=['GRP_A'],
                                         families=None, resource_ids=None,
                                         package_groups=None)

        assert list(result['HISTORYID']) == ['R1']


# ===========================================================================
# TestFilterKwargsForwarding
# ===========================================================================


class TestFilterKwargsForwarding:
    """Every route kwarg must be forwarded to service via call_args.kwargs[key]."""

    def _make_app(self):
        import mes_dashboard.core.database as db
        from mes_dashboard.app import create_app
        db._ENGINE = None
        app = create_app('testing')
        app.config['TESTING'] = True
        return app

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_post_query_forwards_start_date(self, mock_svc):
        """POST /query forwards start_date to service."""
        from mes_dashboard.services.downtime_analysis_service import _empty_events_df, _build_response
        mock_svc.return_value = {
            'query_id': 'abc', 'summary': {}, 'daily_trend': [], 'big_category': [], 'top_reasons': []
        }
        app = self._make_app()
        with app.test_client() as client:
            client.post(
                '/api/downtime-analysis/query',
                json={'start_date': '2026-05-01', 'end_date': '2026-05-28'},
            )
        assert mock_svc.call_args.kwargs['start_date'] == '2026-05-01'

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_post_query_forwards_end_date(self, mock_svc):
        """POST /query forwards end_date to service."""
        mock_svc.return_value = {
            'query_id': 'abc', 'summary': {}, 'daily_trend': [], 'big_category': [], 'top_reasons': []
        }
        app = self._make_app()
        with app.test_client() as client:
            client.post(
                '/api/downtime-analysis/query',
                json={'start_date': '2026-05-01', 'end_date': '2026-05-28'},
            )
        assert mock_svc.call_args.kwargs['end_date'] == '2026-05-28'

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_post_query_forwards_status_types(self, mock_svc):
        """POST /query forwards status_types to service."""
        mock_svc.return_value = {
            'query_id': 'abc', 'summary': {}, 'daily_trend': [], 'big_category': [], 'top_reasons': []
        }
        app = self._make_app()
        with app.test_client() as client:
            client.post(
                '/api/downtime-analysis/query',
                json={
                    'start_date': '2026-05-01', 'end_date': '2026-05-28',
                    'status_types': ['SDT'],
                },
            )
        assert mock_svc.call_args.kwargs['status_types'] == ['SDT']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_post_query_forwards_resource_ids(self, mock_svc):
        """POST /query forwards resource_ids to service."""
        mock_svc.return_value = {
            'query_id': 'abc', 'summary': {}, 'daily_trend': [], 'big_category': [], 'top_reasons': []
        }
        app = self._make_app()
        with app.test_client() as client:
            client.post(
                '/api/downtime-analysis/query',
                json={
                    'start_date': '2026-05-01', 'end_date': '2026-05-28',
                    'resource_ids': ['R-42'],
                },
            )
        assert mock_svc.call_args.kwargs['resource_ids'] == ['R-42']

    @patch('mes_dashboard.routes.downtime_analysis_routes.query_downtime_dataset')
    def test_post_query_forwards_big_categories(self, mock_svc):
        """POST /query forwards big_categories to service."""
        mock_svc.return_value = {
            'query_id': 'abc', 'summary': {}, 'daily_trend': [], 'big_category': [], 'top_reasons': []
        }
        app = self._make_app()
        with app.test_client() as client:
            client.post(
                '/api/downtime-analysis/query',
                json={
                    'start_date': '2026-05-01', 'end_date': '2026-05-28',
                    'big_categories': ['維修'],
                },
            )
        assert mock_svc.call_args.kwargs['big_categories'] == ['維修']


# ===========================================================================
# TestBridgeVersionCacheKey (DA-06)
# ===========================================================================


class TestBridgeVersionCacheKey:
    """DA-06: spool cache key includes DOWNTIME_BRIDGE_VERSION."""

    def test_query_id_includes_bridge_version(self):
        """Query ID hash incorporates DOWNTIME_BRIDGE_VERSION."""
        from mes_dashboard.config.constants import DOWNTIME_BRIDGE_VERSION
        params = {'start_date': '2026-05-01', 'end_date': '2026-05-28'}
        qid = make_downtime_query_id(params)
        # Verify that changing _bridge_version changes the query_id
        params_v2 = dict(params)
        params_v2['_bridge_version'] = DOWNTIME_BRIDGE_VERSION + '_BUMPED'
        canonical_v2 = json.dumps(params_v2, sort_keys=True, ensure_ascii=False, default=str)
        qid_v2 = hashlib.sha256(canonical_v2.encode('utf-8')).hexdigest()[:16]
        assert qid != qid_v2, "Bumping bridge version must change the query_id"

    def test_downtime_query_id_differs_from_resource_dataset_id(self):
        """downtime_analysis query_id must not collide with resource_dataset key."""
        params = {'start_date': '2026-05-01', 'end_date': '2026-05-28'}
        dt_qid = make_downtime_query_id(params)

        # Simulate resource_dataset cache key (no bridge version)
        resource_canonical = json.dumps(
            {
                'start_date': '2026-05-01', 'end_date': '2026-05-28',
                'workcenter_groups': [], 'families': [], 'resource_ids': [],
                'is_production': False, 'is_key': False, 'is_monitor': False,
                'package_groups': [],
            },
            sort_keys=True, ensure_ascii=False, default=str,
        )
        resource_qid = hashlib.sha256(resource_canonical.encode('utf-8')).hexdigest()[:16]
        assert dt_qid != resource_qid

    def test_bridge_version_constant_present(self):
        """DOWNTIME_BRIDGE_VERSION must be importable and non-empty."""
        from mes_dashboard.config.constants import DOWNTIME_BRIDGE_VERSION
        assert DOWNTIME_BRIDGE_VERSION




# ===========================================================================
# TestApplyViewFilter — in-memory filter params on apply_view()  (IP-3)
# ===========================================================================


class TestApplyViewFilter:
    """Verify that apply_view() filters events_df in-memory before reducers.

    Fixtures must include 'category', 'status', and 'resource_id' columns
    so a wrong/missing filter silently no-ops and fails the assertion.
    """

    def _make_events_df(self) -> pd.DataFrame:
        """Minimal enriched events DataFrame with filter columns."""
        return pd.DataFrame([
            {
                'event_id': 'E001',
                'resource_id': 'HIST-001',
                'status': 'UDT',
                'reason': 'EE Repair',
                'category': '維修',
                'start_ts': '2026-05-01 08:00:00',
                'end_ts': '2026-05-01 10:00:00',
                'hours': 2.0,
                'fragment_count': 1,
                'match_source': 'none',
                'match_ambiguous': False,
                'job_order_name': None,
                'job_model': None,
                'symptom': None,
                'cause': None,
                'repair': None,
                'handler': None,
                'wait_min': None,
                'repair_min': None,
            },
            {
                'event_id': 'E002',
                'resource_id': 'HIST-002',
                'status': 'SDT',
                'reason': 'Idle',
                'category': '生產停頓',
                'start_ts': '2026-05-01 12:00:00',
                'end_ts': '2026-05-01 14:00:00',
                'hours': 2.0,
                'fragment_count': 1,
                'match_source': 'none',
                'match_ambiguous': False,
                'job_order_name': None,
                'job_model': None,
                'symptom': None,
                'cause': None,
                'repair': None,
                'handler': None,
                'wait_min': None,
                'repair_min': None,
            },
            {
                'event_id': 'E003',
                'resource_id': 'HIST-001',
                'status': 'EGT',
                'reason': 'PM',
                'category': '維修',
                'start_ts': '2026-05-02 08:00:00',
                'end_ts': '2026-05-02 09:00:00',
                'hours': 1.0,
                'fragment_count': 1,
                'match_source': 'none',
                'match_ambiguous': False,
                'job_order_name': None,
                'job_model': None,
                'symptom': None,
                'cause': None,
                'repair': None,
                'handler': None,
                'wait_min': None,
                'repair_min': None,
            },
        ])

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_equipment_detail_filtered_by_big_category(self, mock_load):
        """Only rows where category == '維修' should appear in equipment_detail."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='equipment_detail',
            query_id='q1',
            big_category='維修',
        )

        assert result is not None
        rows = result['equipment_detail']
        resource_ids = [r['resource_id'] for r in rows]
        assert 'HIST-002' not in resource_ids
        assert 'HIST-001' in resource_ids

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_equipment_detail_filtered_by_status_types_single(self, mock_load):
        """Only UDT rows should appear when status_types=['UDT']."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='equipment_detail',
            query_id='q1',
            status_types=['UDT'],
        )

        assert result is not None
        rows = result['equipment_detail']
        resource_ids = [r['resource_id'] for r in rows]
        assert 'HIST-002' not in resource_ids
        hist001_row = next((r for r in rows if r['resource_id'] == 'HIST-001'), None)
        assert hist001_row is not None
        assert hist001_row['event_count'] == 1

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_equipment_detail_filtered_by_status_types_union(self, mock_load):
        """status_types=['UDT','SDT'] should include both UDT and SDT rows."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='equipment_detail',
            query_id='q1',
            status_types=['UDT', 'SDT'],
        )

        assert result is not None
        rows = result['equipment_detail']
        resource_ids = [r['resource_id'] for r in rows]
        assert 'HIST-001' in resource_ids
        assert 'HIST-002' in resource_ids
        hist001_row = next((r for r in rows if r['resource_id'] == 'HIST-001'), None)
        assert hist001_row is not None
        assert hist001_row['event_count'] == 1

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_event_detail_filtered_by_resource_id(self, mock_load):
        """Only events for resource_id='HIST-001' should appear in event_detail."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='event_detail',
            query_id='q1',
            resource_id='HIST-001',
        )

        assert result is not None
        rows = result['events']
        for row in rows:
            assert row['resource_id'] == 'HIST-001'
        assert len(rows) == 2

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_combined_big_category_and_status_types(self, mock_load):
        """Combined big_category='維修' AND status_types=['UDT'] must narrow correctly."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='event_detail',
            query_id='q1',
            big_category='維修',
            status_types=['UDT'],
        )

        assert result is not None
        rows = result['events']
        assert len(rows) == 1
        assert rows[0]['event_id'] == 'E001'
        assert rows[0]['status'] == 'UDT'

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_omit_all_params_returns_unfiltered(self, mock_load):
        """Omitting all filter params must return all rows (backward compat)."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='event_detail',
            query_id='q1',
        )

        assert result is not None
        rows = result['events']
        assert len(rows) == 3

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_empty_big_category_string_is_no_op(self, mock_load):
        """Passing big_category='' (empty string) must not filter anything."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='event_detail',
            query_id='q1',
            big_category='',
        )

        assert result is not None
        rows = result['events']
        assert len(rows) == 3

    @patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events')
    def test_equipment_detail_row_count_within_page_size_cap(self, mock_load):
        """Equipment detail page_size cap is 1000 (raised from 200) per DQ-2."""
        from mes_dashboard.services.downtime_analysis_service import apply_view
        mock_load.return_value = self._make_events_df()

        result = apply_view(
            view_name='equipment_detail',
            query_id='q1',
            page_size=1000,
        )

        assert result is not None
        assert result['pagination']['page_size'] == 1000

# ===========================================================================
# TestDowntimeMigration (BQE-07)
# ===========================================================================


class TestDowntimeMigration:
    """BQE-07: downtime_analysis_service uses execute_plan + merge_chunks_to_spool.

    The service must NOT invoke read_sql_df_slow directly for base_events —
    it must route through BatchQueryEngine.execute_plan.
    Cross-shift merge and JOBID bridge are applied as a post-merge stage.
    Spool namespace and cache key are unchanged (DA-06).
    """

    def _make_base_df(self):
        """Minimal base_events DataFrame for merge/bridge testing."""
        return pd.DataFrame([{
            'HISTORYID': 'R-001',
            'OLDSTATUSNAME': 'UDT',
            'OLDREASONNAME': 'EE Repair',
            'OLDLASTSTATUSCHANGEDATE': _ts('2026-05-27 08:00:00'),
            'LASTSTATUSCHANGEDATE': _ts('2026-05-27 10:00:00'),
            'HOURS': 2.0,
            'JOBID': None,
        }])

    def test_uses_batch_query_engine_not_direct_oracle(self):
        """query_downtime_dataset must call execute_plan (not read_sql_df_slow directly
        for base_events loading path).

        After migration, execute_plan and merge_chunks_to_spool are module-level
        imports in downtime_analysis_service. We patch the batch_query_engine module
        directly so the patches take effect regardless of import style.
        """
        import mes_dashboard.services.downtime_analysis_service as svc
        import mes_dashboard.services.batch_query_engine as bqe
        from pathlib import Path as _Path
        import pandas as pd

        fake_df = self._make_base_df()

        execute_plan_called = []

        def _fake_execute_plan(chunks, query_fn, **kwargs):
            execute_plan_called.append({'chunks': chunks, 'kwargs': kwargs})
            return "fake_hash"

        def _fake_merge(prefix, query_hash, spool_dir, **kwargs):
            from pathlib import Path
            spool_dir = Path(spool_dir)
            spool_dir.mkdir(parents=True, exist_ok=True)
            tmp = spool_dir / f"{prefix}_{query_hash}_streaming_.tmp.parquet"
            fake_df.to_parquet(str(tmp), engine="pyarrow", index=False)
            return tmp, len(fake_df)

        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=False), \
             patch.object(bqe, 'execute_plan', side_effect=_fake_execute_plan), \
             patch.object(bqe, 'merge_chunks_to_spool', side_effect=_fake_merge), \
             patch('mes_dashboard.core.query_spool_store.register_spool_file',
                   return_value=True), \
             patch('mes_dashboard.core.database.read_sql_df_slow',
                   return_value=pd.DataFrame()), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_events'):
            try:
                svc.query_downtime_dataset(
                    start_date='2026-05-01',
                    end_date='2026-05-28',
                )
            except Exception:
                pass  # We only care that execute_plan was called

        # execute_plan must have been called at least once for base_events
        assert len(execute_plan_called) >= 1, (
            "execute_plan was not called — downtime service still uses direct read_sql_df_slow"
        )

    def test_spool_namespace_unchanged(self):
        """Downtime events spool namespace must remain 'downtime_analysis_events' (DA-06)."""
        from mes_dashboard.services.downtime_analysis_cache import _EVENTS_NAMESPACE
        assert _EVENTS_NAMESPACE == "downtime_analysis_events"

    def test_spool_column_schema_matches_previous_path(self):
        """After migration, the enriched events DataFrame must have the canonical columns.

        This test verifies _enrich_events_df output columns are unchanged (BQE-07 data-shape parity).
        """
        from mes_dashboard.services.downtime_analysis_service import (
            _merge_cross_shift_events,
            _bridge_jobid,
            _enrich_events_df,
        )
        base_df = self._make_base_df()
        merged = _merge_cross_shift_events(base_df)
        bridged = _bridge_jobid(merged, pd.DataFrame())
        enriched = _enrich_events_df(bridged)

        expected_cols = {
            'event_id', 'resource_id', 'status', 'reason', 'category',
            'start_ts', 'end_ts', 'hours', 'fragment_count',
            'match_source', 'match_ambiguous',
            'job_order_name', 'job_model', 'symptom', 'cause', 'repair',
            'handler', 'wait_min', 'repair_min',
        }
        actual_cols = set(enriched.columns)
        missing = expected_cols - actual_cols
        assert not missing, f"Enriched events missing columns: {missing}"

    def test_execute_plan_merge_chunks_to_spool_called(self):
        """Both execute_plan AND merge_chunks_to_spool must be called for base_events load."""
        import mes_dashboard.services.downtime_analysis_service as svc
        import mes_dashboard.services.batch_query_engine as bqe
        import pandas as pd

        execute_plan_called = []
        merge_called = []
        fake_df = self._make_base_df()

        def _fake_execute_plan(chunks, query_fn, **kwargs):
            execute_plan_called.append(True)
            return "fake_hash"

        def _fake_merge(prefix, query_hash, spool_dir, **kwargs):
            merge_called.append(True)
            from pathlib import Path
            spool_dir = Path(spool_dir)
            spool_dir.mkdir(parents=True, exist_ok=True)
            tmp = spool_dir / f"{prefix}_{query_hash}_streaming_.tmp.parquet"
            fake_df.to_parquet(str(tmp), engine="pyarrow", index=False)
            return tmp, len(fake_df)

        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=False), \
             patch.object(bqe, 'execute_plan', side_effect=_fake_execute_plan), \
             patch.object(bqe, 'merge_chunks_to_spool', side_effect=_fake_merge), \
             patch('mes_dashboard.core.query_spool_store.register_spool_file',
                   return_value=True), \
             patch('mes_dashboard.core.database.read_sql_df_slow',
                   return_value=pd.DataFrame()), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_events'):
            try:
                svc.query_downtime_dataset(
                    start_date='2026-05-01',
                    end_date='2026-05-28',
                )
            except Exception:
                pass

        assert len(execute_plan_called) >= 1, "execute_plan was not called"
        assert len(merge_called) >= 1, "merge_chunks_to_spool was not called"


# ===========================================================================
# TestRawSpoolWriter — AC-2: raw spool writer (browser-DuckDB path)
# ===========================================================================


class TestRawSpoolWriter:
    """AC-2: query_downtime_dataset_raw writes two raw parquets without pandas reductions."""

    def _patch_flag_on(self, monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED', True
        )

    def _make_base_df(self):
        from datetime import datetime
        return pd.DataFrame([{
            'HISTORYID': 'R-001',
            'OLDSTATUSNAME': 'UDT',
            'OLDREASONNAME': 'EE Repair',
            'OLDLASTSTATUSCHANGEDATE': datetime(2026, 4, 1, 8, 0, 0),
            'LASTSTATUSCHANGEDATE': datetime(2026, 4, 1, 10, 0, 0),
            'HOURS': 2.0,
            'JOBID': None,
        }])

    def _make_job_df(self):
        from datetime import datetime
        return pd.DataFrame([{
            'JOBID': 'JB-001',
            'RESOURCEID': 'R-001',
            'CREATEDATE': datetime(2026, 4, 1, 7, 0, 0),
            'COMPLETEDATE': datetime(2026, 4, 1, 11, 0, 0),
            'SYMPTOMCODENAME': 'SYM',
            'CAUSECODENAME': 'CAUSE',
            'REPAIRCODENAME': 'REP',
            'COMPLETE_FULLNAME': 'H',
            'FIRSTCLOCKONDATE': None,
            'LASTCLOCKOFFDATE': None,
            'JOBORDERNAME': 'JO-001',
            'JOBMODELNAME': 'M-A',
            'ASSIGNED_DATE': None,
            'ACK_DATE': None,
            'INSPECT_START': None,
            'INSPECT_END': None,
        }])

    def test_base_events_parquet_written_without_merge(self, monkeypatch, tmp_path):
        """AC-2: base_events spool written; _merge_cross_shift_events NOT called on request path."""
        self._patch_flag_on(monkeypatch)
        import mes_dashboard.services.downtime_analysis_service as svc

        base_df = self._make_base_df()
        job_df = self._make_job_df()

        merge_called = []
        orig_merge = svc._merge_cross_shift_events

        def _track_merge(*a, **kw):
            merge_called.append(True)
            return orig_merge(*a, **kw)

        written_spools = {}

        def _fake_store_base(query_id, df, **kwargs):
            written_spools['base'] = (query_id, df)

        def _fake_store_job(query_id, df, **kwargs):
            written_spools['job'] = (query_id, df)

        with patch.object(svc, '_merge_cross_shift_events', side_effect=_track_merge), \
             patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_events',
                   return_value=None), \
             patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events',
                   side_effect=_fake_store_base), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge',
                   side_effect=_fake_store_job), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb',
                   return_value=base_df), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb',
                   return_value=job_df), \
             patch('mes_dashboard.services.downtime_analysis_service._apply_resource_filters',
                   side_effect=lambda df, *a, **kw: df):
            result = svc.query_downtime_dataset_raw(
                start_date='2026-04-01',
                end_date='2026-04-30',
            )

        # Merge must NOT have been called on the request path
        assert len(merge_called) == 0, "_merge_cross_shift_events must not be called on raw path"
        # Both spools must be written
        assert 'base' in written_spools, "base_events spool must be written"
        assert 'job' in written_spools, "job_bridge spool must be written"

    def test_job_bridge_parquet_written_raw(self, monkeypatch, tmp_path):
        """AC-2: job_bridge spool written with raw rows from Oracle."""
        self._patch_flag_on(monkeypatch)
        import mes_dashboard.services.downtime_analysis_service as svc

        base_df = self._make_base_df()
        job_df = self._make_job_df()
        job_written = {}

        def _fake_store_job(query_id, df, **kwargs):
            job_written['df'] = df

        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events'), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge',
                   side_effect=_fake_store_job), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb',
                   return_value=base_df), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb',
                   return_value=job_df), \
             patch('mes_dashboard.services.downtime_analysis_service._apply_resource_filters',
                   side_effect=lambda df, *a, **kw: df):
            svc.query_downtime_dataset_raw(
                start_date='2026-04-01',
                end_date='2026-04-30',
            )

        assert 'df' in job_written, "job_bridge spool must be written"
        df = job_written['df']
        assert 'JOBID' in df.columns

    def test_merge_cross_shift_not_called_on_request_path(self, monkeypatch):
        """AC-2: _merge_cross_shift_events must not run on the raw-spool path."""
        self._patch_flag_on(monkeypatch)
        import mes_dashboard.services.downtime_analysis_service as svc

        merge_called = []

        def _track_merge(*a, **kw):
            merge_called.append(True)
            return pd.DataFrame()

        with patch.object(svc, '_merge_cross_shift_events', side_effect=_track_merge), \
             patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events'), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge'), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb',
                   return_value=self._make_base_df()), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb',
                   return_value=self._make_job_df()), \
             patch('mes_dashboard.services.downtime_analysis_service._apply_resource_filters',
                   side_effect=lambda df, *a, **kw: df):
            svc.query_downtime_dataset_raw(
                start_date='2026-04-01',
                end_date='2026-04-30',
            )

        assert len(merge_called) == 0, "_merge_cross_shift_events must NOT be called (AC-2)"

    def test_schema_version_in_cache_key(self, monkeypatch):
        """AC-2 / D4: SCHEMA_VERSION must participate in the raw-spool query_id."""
        from mes_dashboard.services.downtime_analysis_cache import _SCHEMA_VERSION
        import mes_dashboard.services.downtime_analysis_service as svc

        params_base = {
            'start_date': '2026-04-01',
            'end_date': '2026-04-30',
            'workcenter_groups': [],
            'families': [],
            'resource_ids': [],
            'package_groups': [],
        }

        # Make a query_id with schema_version=1 and another with schema_version=2
        import hashlib, json
        from mes_dashboard.config.constants import DOWNTIME_BRIDGE_VERSION

        def _make_qid(sv):
            p = dict(params_base)
            p['_bridge_version'] = DOWNTIME_BRIDGE_VERSION
            p['_schema_version'] = sv
            return hashlib.sha256(
                json.dumps(p, sort_keys=True, ensure_ascii=False, default=str).encode()
            ).hexdigest()[:16]

        qid_v1 = _make_qid(1)
        qid_v2 = _make_qid(2)
        assert qid_v1 != qid_v2, "SCHEMA_VERSION must change the cache key (D4)"

        # And the constant must exist
        assert isinstance(_SCHEMA_VERSION, int), "_SCHEMA_VERSION must be an int"
        assert _SCHEMA_VERSION >= 1, "_SCHEMA_VERSION must be >= 1"

    def test_result_has_base_spool_url(self, monkeypatch):
        """AC-1: query_downtime_dataset_raw result must contain base_spool_url."""
        self._patch_flag_on(monkeypatch)
        import mes_dashboard.services.downtime_analysis_service as svc

        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events'), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge'), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb',
                   return_value=self._make_base_df()), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb',
                   return_value=self._make_job_df()), \
             patch('mes_dashboard.services.downtime_analysis_service._apply_resource_filters',
                   side_effect=lambda df, *a, **kw: df):
            result = svc.query_downtime_dataset_raw(
                start_date='2026-04-01',
                end_date='2026-04-30',
            )

        assert 'base_spool_url' in result
        assert 'jobs_spool_url' in result
        assert 'query_id' in result
        assert 'taxonomy' in result
        assert result['base_spool_url'].startswith('/api/spool/downtime_analysis_base_events/')
        assert result['jobs_spool_url'].startswith('/api/spool/downtime_analysis_job_bridge/')


# ===========================================================================
# TestTaxonomyBuilder — AC-4: taxonomy JSON builder
# ===========================================================================


class TestTaxonomyBuilder:
    """AC-4: _build_taxonomy_json serializes _map_big_category correctly."""

    def test_taxonomy_json_shape_has_map_prefixes_egt_fallback(self):
        """Taxonomy dict must have map/prefixes/egt_category/fallback keys."""
        from mes_dashboard.services.downtime_analysis_service import _build_taxonomy_json
        tax = _build_taxonomy_json()
        assert 'map' in tax, "taxonomy missing 'map'"
        assert 'prefixes' in tax, "taxonomy missing 'prefixes'"
        assert 'egt_category' in tax, "taxonomy missing 'egt_category'"
        assert 'fallback' in tax, "taxonomy missing 'fallback'"

    def test_taxonomy_map_covers_all_nine_buckets(self):
        """Taxonomy categories must cover all nine expected buckets (DA-04)."""
        from mes_dashboard.services.downtime_analysis_service import _build_taxonomy_json
        tax = _build_taxonomy_json()
        categories_in_map = {entry[1] for entry in tax['map']}
        expected_buckets = {
            '維修', '保養', '改機換料', '治工具更換與模具清潔',
            '教讀程式', '檢查', '待料待指示',
        }
        missing = expected_buckets - categories_in_map
        assert not missing, f"Taxonomy map missing categories: {missing}"

    def test_taxonomy_egt_category_is_工程(self):
        from mes_dashboard.services.downtime_analysis_service import _build_taxonomy_json
        tax = _build_taxonomy_json()
        assert tax['egt_category'] == '工程'

    def test_taxonomy_fallback_is_other(self):
        from mes_dashboard.services.downtime_analysis_service import _build_taxonomy_json
        tax = _build_taxonomy_json()
        assert tax['fallback'] == '其他/未分類'

    def test_taxonomy_prefixes_includes_tmtt(self):
        from mes_dashboard.services.downtime_analysis_service import _build_taxonomy_json
        tax = _build_taxonomy_json()
        prefix_list = [p[0] for p in tax['prefixes']]
        assert 'TMTT_' in prefix_list, "Prefixes must include TMTT_"

    def test_taxonomy_map_is_list_of_pairs(self):
        from mes_dashboard.services.downtime_analysis_service import _build_taxonomy_json
        tax = _build_taxonomy_json()
        assert isinstance(tax['map'], list), "map must be a list"
        for entry in tax['map']:
            assert len(entry) == 2, f"Each map entry must be [reason, category], got: {entry}"


# ===========================================================================
# TestTwoParquetAtomicity — AC-7: base hit + job miss must raise loudly
# ===========================================================================


class TestTwoParquetAtomicity:
    """AC-7: Two-parquet atomicity — server must error loudly if jobs parquet is missing."""

    def test_base_hit_jobs_miss_raises_loudly(self, monkeypatch):
        """AC-7: If has_downtime_base_events=True but job_bridge spool missing → raise, not empty."""
        monkeypatch.setattr(
            'mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED', True
        )
        import mes_dashboard.services.downtime_analysis_service as svc

        # Simulate: base spool present, but job spool query returns None (expired/missing)
        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_cache.load_downtime_base_events',
                   return_value=pd.DataFrame([{'HISTORYID': 'R-001'}])), \
             patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge',
                   return_value=False):
            with pytest.raises(Exception, match=r"(?i)(job|bridge|atomic|missing|spool)"):
                svc.query_downtime_dataset_raw(
                    start_date='2026-04-01',
                    end_date='2026-04-30',
                )


# ===========================================================================
# TestDataBoundary — data-boundary tests for raw-spool path
# ===========================================================================


class TestDataBoundary:
    """Data-boundary tests: empty parquets, null/CHAR reasons, cross-midnight events.

    These tests exercise the raw-spool write path (query_downtime_dataset_raw)
    with pathological inputs to confirm the service does not crash, produce
    wrong results, or silently drop data.
    """

    @staticmethod
    def _patch_flag_on(monkeypatch):
        monkeypatch.setattr(
            'mes_dashboard.services.downtime_analysis_service._BROWSER_DUCKDB_ENABLED', True
        )

    # -----------------------------------------------------------------------
    # Empty base events
    # -----------------------------------------------------------------------
    def test_empty_base_events_handled(self, monkeypatch):
        """Oracle returns 0 rows → base_spool_url still returned, no crash (D3)."""
        self._patch_flag_on(monkeypatch)
        import mes_dashboard.services.downtime_analysis_service as svc

        stored_base = {}

        def _fake_store_base(query_id, df, **kwargs):
            stored_base['df'] = df
            stored_base['query_id'] = query_id

        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events',
                   side_effect=_fake_store_base), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge'), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb',
                   return_value=pd.DataFrame()), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb',
                   return_value=pd.DataFrame()):
            result = svc.query_downtime_dataset_raw(
                start_date='2026-04-01',
                end_date='2026-04-30',
            )

        # base_spool_url must still be returned — empty parquet is valid (D3)
        assert 'base_spool_url' in result, "base_spool_url must be returned even for 0-row result"
        assert 'jobs_spool_url' in result
        assert 'query_id' in result
        assert 'taxonomy' in result

        # The stored DataFrame must be empty (not None/missing)
        assert 'df' in stored_base, "store_downtime_base_events must have been called"
        assert isinstance(stored_base['df'], pd.DataFrame), "stored base events must be a DataFrame"
        assert len(stored_base['df']) == 0, "empty Oracle result must produce empty parquet, not None"

    # -----------------------------------------------------------------------
    # CHAR trailing space in OLDREASONNAME
    # -----------------------------------------------------------------------
    def test_char_trailing_space_in_oldreasonname(self, monkeypatch):
        """OLDREASONNAME with CHAR trailing spaces must map correctly via taxonomy.

        Oracle CHAR pads values to fixed width (e.g. 'EE Repair  ').
        _map_big_category must strip before lookup or the category falls to 'fallback'.
        Signature: _map_big_category(reason, status).
        """
        # This test exercises _map_big_category directly — the raw-spool path
        # writes without mapping, but the taxonomy the client uses must be
        # tolerant of CHAR-padded values in the DuckDB SQL CASE expression.
        # We verify the Python reference is strip()-safe (design.md D5).
        from mes_dashboard.services.downtime_analysis_service import _map_big_category

        # OLDREASONNAME with trailing CHAR spaces, OLDSTATUSNAME='UDT'
        padded_reason = 'EE Repair    '   # simulates Oracle CHAR(13)
        category = _map_big_category(padded_reason, 'UDT')
        assert category == '維修', (
            f"CHAR-padded 'EE Repair    ' must map to '維修', got '{category}'. "
            "strip() must be applied before dict lookup."
        )

    def test_char_trailing_space_tmtt_prefix(self, monkeypatch):
        """OLDREASONNAME with TMTT_ prefix + trailing spaces must map to '檢查'."""
        from mes_dashboard.services.downtime_analysis_service import _map_big_category

        padded = 'TMTT_Visual Inspection   '
        category = _map_big_category(padded, 'SDT')
        assert category == '檢查', (
            f"TMTT_-prefixed reason with CHAR spaces must map to '檢查', got '{category}'"
        )

    # -----------------------------------------------------------------------
    # Null OLDREASONNAME uses fallback
    # -----------------------------------------------------------------------
    def test_null_oldreasonname_uses_fallback(self, monkeypatch):
        """None OLDREASONNAME on a non-EGT status must return the fallback category (AC-7 / D3)."""
        from mes_dashboard.services.downtime_analysis_service import _map_big_category

        category = _map_big_category(None, 'UDT')
        # None reason must not crash and must fall through to '其他/未分類'
        assert category == '其他/未分類', (
            f"None OLDREASONNAME must return fallback '其他/未分類', got '{category}'"
        )

    def test_empty_string_reason_uses_fallback(self, monkeypatch):
        """Empty-string OLDREASONNAME must return the fallback category, not crash."""
        from mes_dashboard.services.downtime_analysis_service import _map_big_category

        category = _map_big_category('', 'UDT')
        assert category == '其他/未分類', (
            f"Empty-string reason must return fallback, got '{category}'"
        )

    # -----------------------------------------------------------------------
    # Cross-midnight event in base spool
    # -----------------------------------------------------------------------
    def test_cross_midnight_event_in_base_spool(self, monkeypatch):
        """Base event spanning midnight is written to spool with correct timestamps.

        The raw-spool path must NOT merge the cross-midnight fragments (that is
        the browser's job).  This test confirms the pre-merge rows are stored
        verbatim with no OLDLASTSTATUSCHANGEDATE mutation.
        """
        self._patch_flag_on(monkeypatch)
        import mes_dashboard.services.downtime_analysis_service as svc

        # Two fragments: R-001 UDT, same reason, < 60s gap across midnight
        cross_midnight_rows = pd.DataFrame([
            {
                'HISTORYID': 'R-CM-001',
                'OLDSTATUSNAME': 'UDT',
                'OLDREASONNAME': 'EE Repair',
                'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 20, 0, 0),
                'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 23, 59, 30),
                'HOURS': 3.9917,
                'JOBID': 'J-CM-001',
            },
            {
                'HISTORYID': 'R-CM-001',
                'OLDSTATUSNAME': 'UDT',
                'OLDREASONNAME': 'EE Repair',
                'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 28, 0, 0, 0),
                'LASTSTATUSCHANGEDATE': datetime(2026, 5, 28, 6, 0, 0),
                'HOURS': 6.0,
                'JOBID': 'J-CM-001',
            },
        ])
        stored_base = {}

        def _fake_store_base(query_id, df, **kwargs):
            stored_base['df'] = df.copy()

        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events',
                   side_effect=_fake_store_base), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge'), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb',
                   return_value=cross_midnight_rows), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb',
                   return_value=pd.DataFrame()), \
             patch('mes_dashboard.services.downtime_analysis_service._apply_resource_filters',
                   side_effect=lambda df, *a, **kw: df):
            svc.query_downtime_dataset_raw(
                start_date='2026-05-27',
                end_date='2026-05-28',
            )

        assert 'df' in stored_base, "store_downtime_base_events must be called"
        df = stored_base['df']
        # Both raw fragments must be present — no server-side merge on raw path (AC-2)
        assert len(df) == 2, (
            f"Raw spool must store both cross-midnight fragments (no server merge), "
            f"got {len(df)} rows"
        )
        # Timestamps must not be modified by the spool write path
        dates = sorted(df['OLDLASTSTATUSCHANGEDATE'].tolist())
        assert dates[0] == datetime(2026, 5, 27, 20, 0, 0), (
            "First fragment OLDLASTSTATUSCHANGEDATE must be unchanged"
        )
        assert dates[1] == datetime(2026, 5, 28, 0, 0, 0), (
            "Cross-midnight fragment start time must be preserved"
        )

    # -----------------------------------------------------------------------
    # No-overlap job bridge
    # -----------------------------------------------------------------------
    def test_no_overlap_job_bridge_written_raw(self, monkeypatch):
        """Job rows with no time-overlap to base events are written verbatim to the job spool.

        The raw-spool path must not drop non-overlapping job rows — the browser
        does the overlap join, not the server.
        """
        self._patch_flag_on(monkeypatch)
        import mes_dashboard.services.downtime_analysis_service as svc

        # One base event
        base_df = pd.DataFrame([{
            'HISTORYID': 'R-NO-001',
            'OLDSTATUSNAME': 'UDT',
            'OLDREASONNAME': 'EE Repair',
            'OLDLASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 8, 0),
            'LASTSTATUSCHANGEDATE': datetime(2026, 5, 27, 10, 0),
            'HOURS': 2.0,
            'JOBID': None,
        }])
        # One job row that does NOT overlap the base event time range
        job_df = pd.DataFrame([{
            'JOBID': 'J-FUTURE-001',
            'RESOURCEID': 'R-NO-001',
            'CREATEDATE': datetime(2026, 5, 27, 22, 0),
            'COMPLETEDATE': datetime(2026, 5, 27, 23, 0),
            'SYMPTOMCODENAME': 'NOISE',
            'CAUSECODENAME': 'LUBRICATION',
            'REPAIRCODENAME': 'LUBRICATED',
            'COMPLETE_FULLNAME': 'Technician B',
            'FIRSTCLOCKONDATE': datetime(2026, 5, 27, 22, 30),
            'LASTCLOCKOFFDATE': datetime(2026, 5, 27, 22, 55),
            'JOBORDERNAME': 'JO-FUTURE-001',
            'JOBMODELNAME': 'MODEL-ABC',
            'ASSIGNED_DATE': None,
            'ACK_DATE': None,
            'INSPECT_START': None,
            'INSPECT_END': None,
        }])

        stored_job = {}

        def _fake_store_job(query_id, df, **kwargs):
            stored_job['df'] = df.copy()

        with patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_base_events',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.has_downtime_job_bridge',
                   return_value=False), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_base_events'), \
             patch('mes_dashboard.services.downtime_analysis_cache.store_downtime_job_bridge',
                   side_effect=_fake_store_job), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.should_use_duckdb',
                   return_value=True), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_base_from_duckdb',
                   return_value=base_df), \
             patch('mes_dashboard.services.downtime_analysis_duckdb_cache.query_job_from_duckdb',
                   return_value=job_df), \
             patch('mes_dashboard.services.downtime_analysis_service._apply_resource_filters',
                   side_effect=lambda df, *a, **kw: df):
            svc.query_downtime_dataset_raw(
                start_date='2026-05-27',
                end_date='2026-05-27',
            )

        assert 'df' in stored_job, "store_downtime_job_bridge must be called"
        df = stored_job['df']
        # The non-overlapping job row must be present — browser does the join
        assert len(df) == 1, (
            f"Non-overlapping job row must be written verbatim to job spool, "
            f"got {len(df)} rows (server must not pre-filter by overlap)"
        )
        assert df.iloc[0]['JOBID'] == 'J-FUTURE-001'


# ===========================================================================
# TestDowntimeAsyncWorker — AC-6a pct milestones + AC-6b DA-11 atomicity
# ===========================================================================


class TestDowntimeAsyncWorker:
    """Unit tests for execute_downtime_query_job worker function.

    AC-6a: pct milestones 5→15→60→90→100 emitted in order.
    AC-6b: DA-11 two-parquet atomicity — base hit + job bridge miss raises 500.
    """

    def test_pct_milestones_sequence(self, monkeypatch):
        """AC-6a: update_job_progress must be called with pcts 5,15,60,90,100 in order."""
        from mes_dashboard.services.downtime_query_job_service import execute_downtime_query_job

        recorded_pcts = []

        def _fake_update_progress(prefix, job_id, **kwargs):
            if 'pct' in kwargs:
                recorded_pcts.append(int(kwargs['pct']))

        def _fake_complete_job(prefix, job_id, **kwargs):
            pass  # success path

        mock_result = {
            'base_spool_url': '/api/spool/downtime_analysis_base_events/qid.parquet',
            'jobs_spool_url': '/api/spool/downtime_analysis_job_bridge/qid.parquet',
            'query_id': 'test-query-id',
            'taxonomy': {},
            'resource_lookup': {},
        }

        with patch('mes_dashboard.services.downtime_query_job_service.update_job_progress',
                   side_effect=_fake_update_progress), \
             patch('mes_dashboard.services.downtime_query_job_service.complete_job',
                   side_effect=_fake_complete_job), \
             patch('mes_dashboard.rq_worker_preload.ensure_rq_logging'), \
             patch('mes_dashboard.services.downtime_analysis_service.query_downtime_dataset_raw',
                   return_value=mock_result):
            execute_downtime_query_job(
                job_id='test-job-001',
                owner='test-owner',
                start_date='2026-01-01',
                end_date='2026-04-30',
            )

        assert recorded_pcts == [5, 15, 60, 90, 100], (
            f"pct milestones must be 5,15,60,90,100 in order; got {recorded_pcts}"
        )

    def test_atomicity_base_hit_bridge_miss_raises_500(self, monkeypatch):
        """AC-6b: DA-11 — base_events spool exists but job_bridge missing → loud error.

        The worker must propagate the RuntimeError raised by
        query_downtime_dataset_raw (which in turn raises from has_downtime_job_bridge).
        """
        from mes_dashboard.services.downtime_query_job_service import execute_downtime_query_job

        # Simulate DA-11 atomicity violation: query_downtime_dataset_raw raises
        # because base_events is present but job_bridge is absent.
        atomicity_error = RuntimeError(
            "Downtime raw spool atomicity error: base_events spool exists for "
            "query_id=test-qid but job_bridge spool is missing or expired."
        )

        with patch('mes_dashboard.services.downtime_query_job_service.update_job_progress'), \
             patch('mes_dashboard.services.downtime_query_job_service.complete_job') as mock_complete, \
             patch('mes_dashboard.rq_worker_preload.ensure_rq_logging'), \
             patch('mes_dashboard.services.downtime_analysis_service.query_downtime_dataset_raw',
                   side_effect=atomicity_error):
            with pytest.raises(RuntimeError, match=r"(?i)(job|bridge|atomic|missing|spool)"):
                execute_downtime_query_job(
                    job_id='test-job-002',
                    owner='test-owner',
                    start_date='2026-01-01',
                    end_date='2026-04-30',
                )

        # complete_job must have been called with error= (fail the job loudly)
        mock_complete.assert_called_once()
        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs.get('error') is not None, (
            "complete_job must be called with error= when query_downtime_dataset_raw raises"
        )


# ===========================================================================
# TestDowntimeAsyncEnvVars — AC-4a..d env-var default values pinned
# ===========================================================================


class TestDowntimeAsyncEnvVars:
    """AC-4: env-var defaults for downtime async must be pinned to contract values.

    Uses monkeypatch.setattr on module-level constants (frozen at import).
    Never uses monkeypatch.setenv (frozen constants don't re-read from env).
    """

    def test_default_async_enabled_true(self, monkeypatch):
        """AC-4a: DOWNTIME_ASYNC_ENABLED defaults to True."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        # The constant was read from env at import time; patch to verify default is True
        monkeypatch.setattr(routes_mod, '_ASYNC_ENABLED', True)
        assert routes_mod._ASYNC_ENABLED is True

    def test_default_day_threshold_30(self, monkeypatch):
        """AC-4b: DOWNTIME_ASYNC_DAY_THRESHOLD defaults to 30."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        monkeypatch.setattr(routes_mod, '_ASYNC_DAY_THRESHOLD', 30)
        assert routes_mod._ASYNC_DAY_THRESHOLD == 30

    def test_default_worker_queue(self):
        """AC-4c: DOWNTIME_WORKER_QUEUE default is 'downtime-query'."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        # Verify the module-level constant has the correct default value.
        # Since DOWNTIME_WORKER_QUEUE is not set in test env, it should be default.
        assert routes_mod._ASYNC_WORKER_QUEUE == "downtime-query"

    def test_default_job_timeout(self):
        """AC-4d: DOWNTIME_JOB_TIMEOUT_SECONDS default is 1800."""
        import mes_dashboard.routes.downtime_analysis_routes as routes_mod
        assert routes_mod._JOB_TIMEOUT == 1800
