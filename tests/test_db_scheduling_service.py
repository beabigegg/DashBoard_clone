# -*- coding: utf-8 -*-
"""Unit tests for db_scheduling_service.get_db_scheduling_queue().

Tests cover:
- DB-01: D/B-START lot identification
- DB-02: Primary WORKFLOWNAME match → matchSource='workflow'
- DB-03: BOP fallback routing (U/E/P prefixes) → matchSource='bop-fallback'
- DB-03: Unknown/null BOP → zero rows, no error (matchSource='none')
- DB-04: Sort order PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS, NULLS LAST
- Cache-miss path (get_cached_wip_data returns None)
- DB-00 SPEC list membership pinned via constant
"""

from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch

from mes_dashboard.services.db_scheduling_service import (
    get_db_scheduling_queue,
    DB_PROCESS_SPECS,
    BOP_FALLBACK_GROUPS,
)


# ---------------------------------------------------------------------------
# DB-00 membership pin
# ---------------------------------------------------------------------------

class TestDb00SpecList:
    """DB-00: Pin the 12-SPEC list so drift from business-rules.md is caught."""

    def test_db_process_specs_has_12_items(self):
        assert len(DB_PROCESS_SPECS) == 12

    def test_db_process_specs_contains_all_expected(self):
        expected = frozenset([
            '1DB', '1DB1WB', '1DB2WB', '2DB', '2DB1WB', '2DB2WB',
            'DBCB', 'Epoxy D/B', 'Eutectic D/B', 'Eutectic D/B-雙晶',
            'Solder Paste D/B+E-Clip', '錫膏網印',
        ])
        assert DB_PROCESS_SPECS == expected

    def test_bop_fallback_groups_union_subset_of_db_process_specs(self):
        """Every spec in BOP_FALLBACK_GROUPS must be in DB_PROCESS_SPECS."""
        all_fallback_specs = set()
        for specs in BOP_FALLBACK_GROUPS.values():
            all_fallback_specs.update(specs)
        assert all_fallback_specs <= DB_PROCESS_SPECS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_wip_df(**kwargs):
    """Return a minimal WIP DataFrame row as dict, merged with kwargs."""
    defaults = {
        'LOTID': 'LOT001',
        'WORKFLOWNAME': 'WF-A',
        'PACKAGE_LEF': 'SOT-23',
        'PJ_TYPE': 'TypeA',
        'WAFERLOT': 'WL-001',
        'UTS': '2026/01/15',
        'QTY': 100,
        'BOP': 'U-Eutectic',
        'SPECNAME': 'D/B-START',
        'STATUS': 'ACTIVE',
        'EQUIPMENTS': None,
    }
    defaults.update(kwargs)
    return defaults


def _df(*rows):
    """Build a DataFrame from a list of row dicts."""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# AC-1: D/B-START lot identification
# ---------------------------------------------------------------------------

class TestStartLotFiltering:
    """AC-1 / DB-01: only rows with SPECNAME='D/B-START' are start lots."""

    def test_start_lots_filtered_by_specname(self):
        """Only lots whose SPECNAME == 'D/B-START' appear as candidates."""
        wip = _df(
            _make_wip_df(LOTID='LOT-DB-START', SPECNAME='D/B-START', BOP='U-test'),
            _make_wip_df(LOTID='LOT-OTHER', SPECNAME='1DB', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', WORKFLOWNAME='WF-A'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        lot_ids = {r['lotId'] for r in result}
        # LOT-DB-START is a start lot (SPECNAME='D/B-START').
        # LOT-OTHER is a running-eqp candidate, not a start lot.
        assert 'LOT-OTHER' not in lot_ids

    def test_null_bop_returns_empty_rows(self):
        """A D/B-START lot with null BOP and no workflow match yields zero rows, no exception."""
        wip = _df(
            # Start lot with null BOP and workflow WF-ORPHAN (no match in running pool)
            _make_wip_df(LOTID='LOT-NULL-BOP', SPECNAME='D/B-START',
                         BOP=None, WORKFLOWNAME='WF-ORPHAN'),
            # Running lot in Eutectic group with DIFFERENT workflow → no primary match
            _make_wip_df(LOTID='EQ-LOT', SPECNAME='Eutectic D/B',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-001', WORKFLOWNAME='WF-A'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        lot_ids = {r['lotId'] for r in result}
        # Null BOP with no workflow match → matchSource='none' → zero rows
        assert 'LOT-NULL-BOP' not in lot_ids
        assert result == []


# ---------------------------------------------------------------------------
# AC-2: Primary WORKFLOWNAME match
# ---------------------------------------------------------------------------

class TestWorkflowMatch:
    """AC-2 / DB-02: primary match on WORKFLOWNAME gives matchSource='workflow'."""

    def test_workflow_match_primary(self):
        """When WORKFLOWNAME matches a running-eqp row, matchSource='workflow'."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-ALPHA', BOP='U-test'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='1DB',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-001',
                         WORKFLOWNAME='WF-ALPHA'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        workflow_rows = [r for r in result if r['lotId'] == 'START-LOT']
        assert len(workflow_rows) >= 1
        assert all(r['matchSource'] == 'workflow' for r in workflow_rows)

    def test_workflow_match_sets_equipment(self):
        """The matched equipment from EQUIPMENTS is propagated to 'equipment'."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-ALPHA', BOP=None),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-007',
                         WORKFLOWNAME='WF-ALPHA'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        workflow_rows = [r for r in result if r['lotId'] == 'START-LOT']
        assert any(r['equipment'] == 'EQ-007' for r in workflow_rows)

    def test_workflow_match_requires_active_status(self):
        """Running-eqp pool only includes STATUS='ACTIVE' rows."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-ALPHA', BOP=None),
            # This RUN lot has ACTIVE=False — should NOT be in pool
            _make_wip_df(LOTID='RUN-HOLD', SPECNAME='1DB',
                         STATUS='HOLD', EQUIPMENTS='EQ-HOLD',
                         WORKFLOWNAME='WF-ALPHA'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        # No match → no rows (null BOP → matchSource=none → zero rows)
        assert result == []

    def test_workflow_match_requires_non_null_equipments(self):
        """EQUIPMENTS IS NULL rows are excluded from primary match pool."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-ALPHA', BOP=None),
            _make_wip_df(LOTID='RUN-NO-EQ', SPECNAME='1DB',
                         STATUS='ACTIVE', EQUIPMENTS=None,
                         WORKFLOWNAME='WF-ALPHA'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        assert result == []


# ---------------------------------------------------------------------------
# AC-3: BOP fallback
# ---------------------------------------------------------------------------

class TestBopFallback:
    """AC-3 / DB-03: BOP first-char dispatch to equipment groups."""

    def _start_lot(self, bop):
        return _make_wip_df(LOTID='START-LOT', SPECNAME='D/B-START',
                            WORKFLOWNAME='NO-MATCH-WF', BOP=bop)

    def _running_lot(self, specname, eqp='EQ-RUN'):
        return _make_wip_df(LOTID=f'RUN-{specname}', SPECNAME=specname,
                            STATUS='ACTIVE', EQUIPMENTS=eqp,
                            WORKFLOWNAME='OTHER-WF')

    def test_bop_fallback_U(self):
        """BOP[0]='U' → equipment from Eutectic/1DB/2DB group, matchSource='bop-fallback'."""
        wip = _df(
            self._start_lot('U-test'),
            self._running_lot('Eutectic D/B', 'EQ-EUTECTIC'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        assert len(result) >= 1
        assert all(r['matchSource'] == 'bop-fallback' for r in result)
        assert any(r['equipment'] == 'EQ-EUTECTIC' for r in result)

    def test_bop_fallback_E(self):
        """BOP[0]='E' → equipment from Epoxy D/B group, matchSource='bop-fallback'."""
        wip = _df(
            self._start_lot('E-epoxy'),
            self._running_lot('Epoxy D/B', 'EQ-EPOXY'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        assert len(result) >= 1
        assert all(r['matchSource'] == 'bop-fallback' for r in result)
        assert any(r['equipment'] == 'EQ-EPOXY' for r in result)

    def test_bop_fallback_P(self):
        """BOP[0]='P' → equipment from DBCB/Solder Paste group, matchSource='bop-fallback'."""
        wip = _df(
            self._start_lot('P-paste'),
            self._running_lot('DBCB', 'EQ-DBCB'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        assert len(result) >= 1
        assert all(r['matchSource'] == 'bop-fallback' for r in result)
        assert any(r['equipment'] == 'EQ-DBCB' for r in result)

    def test_bop_fallback_unknown(self):
        """BOP[0] not in U/E/P → matchSource='none', zero rows emitted."""
        wip = _df(
            self._start_lot('X-unknown'),
            self._running_lot('1DB', 'EQ-1DB'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        assert result == []

    def test_bop_fallback_no_match_source_none_is_not_emitted(self):
        """matchSource='none' rows are never included in output."""
        wip = _df(
            self._start_lot('Z-other'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        none_rows = [r for r in result if r.get('matchSource') == 'none']
        assert none_rows == []

    def test_bop_fallback_only_fires_when_no_workflow_match(self):
        """If workflow match succeeds, BOP fallback is not applied."""
        wip = _df(
            # Start lot with BOP='U-...' AND same WORKFLOWNAME as running lot
            _make_wip_df(LOTID='START-LOT', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-A', BOP='U-test'),
            # Running lot: same WORKFLOWNAME → primary match
            _make_wip_df(LOTID='RUN-1DB', SPECNAME='1DB',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-1DB',
                         WORKFLOWNAME='WF-A'),
            # Another lot in Eutectic group: different WORKFLOWNAME
            _make_wip_df(LOTID='RUN-EUTECTIC', SPECNAME='Eutectic D/B',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-EUTECTIC',
                         WORKFLOWNAME='WF-B'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        # All rows for START-LOT should be 'workflow', not 'bop-fallback'
        start_rows = [r for r in result if r['lotId'] == 'START-LOT']
        assert len(start_rows) >= 1
        assert all(r['matchSource'] == 'workflow' for r in start_rows)


# ---------------------------------------------------------------------------
# AC-4: Sort order NULLS LAST
# ---------------------------------------------------------------------------

class TestSortOrder:
    """AC-4 / DB-04: sort PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS, NULLS LAST."""

    def test_sort_order_nulls_last(self):
        """Null sort-key values appear after non-null values."""
        wip = _df(
            # Running equipment rows (used by both start lots via BOP fallback)
            _make_wip_df(LOTID='RUN1', SPECNAME='Eutectic D/B',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-001',
                         WORKFLOWNAME='WF-NOMATCH'),
            # Start lots: one with nulls, one fully populated
            _make_wip_df(LOTID='LOT-FULL', SPECNAME='D/B-START',
                         PACKAGE_LEF='SOT-23', PJ_TYPE='TypeA',
                         WAFERLOT='WL-A', UTS='2026/01/01',
                         BOP='U-test', WORKFLOWNAME='WF-NOMATCH'),
            _make_wip_df(LOTID='LOT-NULL', SPECNAME='D/B-START',
                         PACKAGE_LEF=None, PJ_TYPE=None,
                         WAFERLOT=None, UTS=None,
                         BOP='U-test', WORKFLOWNAME='WF-NOMATCH'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()

        assert len(result) >= 2

        full_idx = next(
            i for i, r in enumerate(result) if r['lotId'] == 'LOT-FULL'
        )
        null_idx = next(
            i for i, r in enumerate(result) if r['lotId'] == 'LOT-NULL'
        )
        # LOT-FULL (non-null keys) must sort BEFORE LOT-NULL (null keys = LAST)
        assert full_idx < null_idx

    def test_sort_primary_key_is_package_lef(self):
        """PACKAGE_LEF is the first sort key (ASC)."""
        wip = _df(
            _make_wip_df(LOTID='RUN1', SPECNAME='Eutectic D/B',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-001',
                         WORKFLOWNAME='WF-NOMATCH'),
            _make_wip_df(LOTID='LOT-B', SPECNAME='D/B-START',
                         PACKAGE_LEF='ZZ-LAST', BOP='U-test',
                         WORKFLOWNAME='WF-NOMATCH'),
            _make_wip_df(LOTID='LOT-A', SPECNAME='D/B-START',
                         PACKAGE_LEF='AA-FIRST', BOP='U-test',
                         WORKFLOWNAME='WF-NOMATCH'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()

        lot_ids = [r['lotId'] for r in result]
        assert lot_ids.index('LOT-A') < lot_ids.index('LOT-B')


# ---------------------------------------------------------------------------
# AC-5: matchSource=none emits zero rows
# ---------------------------------------------------------------------------

class TestNoMatchNoBop:
    """AC-5 / DB-03 null path: no workflow match + null/unknown BOP → zero rows."""

    def test_no_match_no_bop_returns_none_source(self):
        """Lot with null BOP and no workflow match produces no output rows."""
        wip = _df(
            _make_wip_df(LOTID='START-ORPHAN', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-ORPHAN', BOP=None),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        # matchSource=none → zero rows (not included in output)
        assert result == []


# ---------------------------------------------------------------------------
# Cache-miss fallback path
# ---------------------------------------------------------------------------

class TestCacheMissFallback:
    """Service must not 500 when get_cached_wip_data() returns None."""

    def test_cache_miss_returns_empty_list(self):
        """When cache returns None, result is an empty list (no exception)."""
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=None,
        ):
            # Also patch read_sql_df to return None (simulating CI-without-Oracle)
            with patch(
                'mes_dashboard.services.db_scheduling_service.read_sql_df',
                return_value=None,
            ):
                result = get_db_scheduling_queue()
        assert result == []

    def test_cache_miss_with_oracle_fallback_returns_data(self):
        """When cache misses, Oracle fallback is attempted and data is returned."""
        oracle_df = _df(
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-FBK',
                         WORKFLOWNAME='WF-FALLBACK'),
            _make_wip_df(LOTID='START-LOT', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-FALLBACK', BOP=None),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=None,
        ):
            with patch(
                'mes_dashboard.services.db_scheduling_service.read_sql_df',
                return_value=oracle_df,
            ):
                result = get_db_scheduling_queue()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Row shape / field names
# ---------------------------------------------------------------------------

class TestRowShape:
    """Each output row has the 15 required fields per §3.22."""

    REQUIRED_FIELDS = {
        # Waiting lot
        'lotId', 'workflowName', 'packageLef', 'pjType', 'waferLot',
        'uts', 'qty', 'bop',
        # Running lot on candidate equipment (priority-column key)
        'eqpPackageLef', 'eqpPjType', 'eqpWaferLot', 'eqpUts',
        # Dispatch metadata
        'targetSpec', 'equipment', 'matchSource',
    }

    def test_row_has_all_required_fields(self):
        wip = _df(
            _make_wip_df(LOTID='START', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-A', BOP=None),
            _make_wip_df(LOTID='RUN', SPECNAME='1DB',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-001',
                         WORKFLOWNAME='WF-A'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        assert len(result) >= 1
        for row in result:
            assert self.REQUIRED_FIELDS <= set(row.keys()), (
                f"Row missing fields: {self.REQUIRED_FIELDS - set(row.keys())}"
            )

    def test_eqp_fields_come_from_running_lot_not_start_lot(self):
        """eqpPackageLef/eqpPjType/eqpWaferLot/eqpUts must reflect the equipment's
        running lot, not the waiting start lot."""
        wip = _df(
            _make_wip_df(LOTID='START', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-A', BOP=None,
                         PACKAGE_LEF='WAIT-PKG', PJ_TYPE='WAIT-PJ',
                         WAFERLOT='WAIT-WL', UTS='2026/01/01'),
            _make_wip_df(LOTID='RUN', SPECNAME='1DB',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-001',
                         WORKFLOWNAME='WF-A',
                         PACKAGE_LEF='RUN-PKG', PJ_TYPE='RUN-PJ',
                         WAFERLOT='RUN-WL', UTS='2026/06/01'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        assert len(result) == 1
        row = result[0]
        # Lot fixed columns come from the waiting lot
        assert row['packageLef'] == 'WAIT-PKG'
        assert row['pjType'] == 'WAIT-PJ'
        # Eqp priority key comes from the running lot on the machine
        assert row['eqpPackageLef'] == 'RUN-PKG'
        assert row['eqpPjType'] == 'RUN-PJ'
        assert row['eqpWaferLot'] == 'RUN-WL'
        assert row['eqpUts'] == '2026/06/01'

    def test_qty_is_integer(self):
        wip = _df(
            _make_wip_df(LOTID='START', SPECNAME='D/B-START',
                         WORKFLOWNAME='WF-A', BOP=None, QTY=50),
            _make_wip_df(LOTID='RUN', SPECNAME='1DB',
                         STATUS='ACTIVE', EQUIPMENTS='EQ-001',
                         WORKFLOWNAME='WF-A'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ):
            result = get_db_scheduling_queue()
        for row in result:
            assert isinstance(row['qty'], int)
