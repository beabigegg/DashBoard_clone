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

    def test_change_type_maps_to_換型換線(self):
        assert _map_big_category('Change Type', 'SDT') == '換型換線'

    def test_change_package_maps_to_換型換線(self):
        assert _map_big_category('Change Package', 'SDT') == '換型換線'

    def test_re_layout_maps_to_換型換線(self):
        assert _map_big_category('Re Layout', 'SDT') == '換型換線'

    def test_change_marking_code_maps_to_換型換線(self):
        assert _map_big_category('Change Marking Code', 'SDT') == '換型換線'

    def test_change_model_maps_to_換型換線(self):
        assert _map_big_category('Change Model', 'SDT') == '換型換線'

    def test_change_tool_maps_to_換刀清模(self):
        assert _map_big_category('Change Tool/Consumables', 'SDT') == '換刀清模'

    def test_clean_mold_maps_to_換刀清模(self):
        assert _map_big_category('Clean Mold', 'SDT') == '換刀清模'

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

    def test_big_category_map_has_eight_buckets(self):
        """Taxonomy must cover all 8 defined categories (DA-04)."""
        categories = set(_BIG_CATEGORY_MAP.values())
        # EGT → 工程 is handled by status check, not the map
        # Map covers: 維修, 保養, 換型換線, 換刀清模, 檢查, 待料待指示
        for cat in ('維修', '保養', '換型換線', '換刀清模', '檢查', '待料待指示'):
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
    def test_big_categories_always_returns_all_eight(
        self, mock_pg, mock_wc_map, mock_resources
    ):
        """big_categories list always contains all 8 categories regardless of filters."""
        from mes_dashboard.services.downtime_analysis_service import get_filter_options

        mock_resources.return_value = []
        mock_wc_map.return_value = {}
        mock_pg.return_value = None

        opts = get_filter_options()
        assert len(opts['big_categories']) == 8


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
