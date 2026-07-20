# -*- coding: utf-8 -*-
"""Unit tests for db_scheduling_service.get_db_scheduling_queue().

Rewritten 2026-07 for the business-rule change that replaced the
D/B-START/WORKFLOWNAME matching model with a 晶片切割-END/BOP+PACKAGE+zone
model (see db_scheduling_service.py module docstring for the full rule).

Tests cover:
- DB-00: SPEC list membership pinned via constant (unchanged)
- DB-01: 晶片切割-END lot identification (replaces D/B-START)
- Single-tier match: condition (a) BOP-derived SPEC group, condition (b)
  PACKAGE equality, condition (c) BOP-derived equipment zone
  - BOP='U': zone depends on the waiting lot's own PJ_PRODUCEREGION
    (A棟 → {A,B,C}; D區 → {D}; any other region incl. 'E區'/None → zero rows)
  - BOP='E': zone fixed to 焊接D區 regardless of the waiting lot's region
  - BOP='P': zone fixed to 焊接E區 regardless of the waiting lot's region
  - Unknown/null BOP → zero rows, no error
  - PACKAGE mismatch → zero candidates
- Idle-equipment history fallback (equipmentSource='history'):
  match / no-history-data / spec-not-allowed / package-mismatch / wrong-zone
- DB-04: Sort order PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS, NULLS LAST
- Cache-miss path (get_cached_wip_data returns None)
- Row shape: 16 required fields including the new 'equipmentSource'
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
# DB-00 membership pin (unchanged by the 2026-07 rewrite)
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
        all_grouped_specs = set()
        for specs in BOP_FALLBACK_GROUPS.values():
            all_grouped_specs.update(specs)
        assert all_grouped_specs <= DB_PROCESS_SPECS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_wip_df(**kwargs):
    """Return a minimal WIP DataFrame row as dict, merged with kwargs."""
    defaults = {
        'LOTID': 'LOT001',
        'WORKFLOWNAME': 'WF-A',
        'PACKAGE_LEF': 'PKG-DEFAULT',
        'PJ_TYPE': 'TypeA',
        'WAFERLOT': 'WL-001',
        'UTS': '2026/01/15',
        'QTY': 100,
        'BOP': 'U-Eutectic',
        'SPECNAME': '晶片切割-END',
        'STATUS': 'ACTIVE',
        'EQUIPMENTS': None,
        'PJ_PRODUCEREGION': 'A棟',
    }
    defaults.update(kwargs)
    return defaults


def _df(*rows):
    """Build a DataFrame from a list of row dicts."""
    return pd.DataFrame(rows)


def _resource(name, workcenter='焊接_DB', location='焊接A區'):
    """Build a resource_cache.get_all_resources()-shaped record."""
    return {'RESOURCENAME': name, 'WORKCENTERNAME': workcenter, 'LOCATIONNAME': location}


def _idle_history_df(**rows_kwargs):
    """Build a single-row DataFrame shaped like the idle_equipment_history.sql result."""
    defaults = {
        'EQUIPMENTNAME': 'EQ-IDLE',
        'SPECNAME': 'Eutectic D/B',
        'PACKAGE_LF': 'PKG-DEFAULT',
        'TRACKOUTTIMESTAMP': pd.Timestamp('2026-07-01'),
    }
    defaults.update(rows_kwargs)
    return pd.DataFrame([defaults])


def _run_queue(wip_df, resources=None, idle_history_df=None):
    """Run get_db_scheduling_queue() with the WIP cache, resource cache, and
    idle-equipment-history Oracle query all mocked.

    resources: list of resource_cache records (defaults to [] — resource
        cache unavailable/empty, which is fail-closed: zero zone matches).
    idle_history_df: DataFrame returned by the idle-equipment-history
        read_sql_df() call (defaults to None — no idle-history rows).
    """
    with patch(
        'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
        return_value=wip_df,
    ), patch(
        'mes_dashboard.services.resource_cache.get_all_resources',
        return_value=resources or [],
    ), patch(
        'mes_dashboard.services.db_scheduling_service.read_sql_df',
        return_value=idle_history_df,
    ):
        return get_db_scheduling_queue()


# ---------------------------------------------------------------------------
# DB-01: 晶片切割-END lot identification
# ---------------------------------------------------------------------------

class TestStartLotFiltering:
    """DB-01: only rows with SPECNAME='晶片切割-END' are start lots."""

    def test_start_lots_filtered_by_specname(self):
        """Only lots whose SPECNAME == '晶片切割-END' appear as candidates."""
        wip = _df(
            _make_wip_df(LOTID='LOT-CUT-END', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟',
                         PACKAGE_LEF='PKG-A'),
            _make_wip_df(LOTID='LOT-OTHER-SPEC', SPECNAME='其他站', STATUS='ACTIVE'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF='PKG-A'),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        lot_ids = {r['lotId'] for r in result}
        assert 'LOT-CUT-END' in lot_ids
        assert 'LOT-OTHER-SPEC' not in lot_ids
        # RUN-LOT is a candidate equipment's own lot, never an output lotId
        assert 'RUN-LOT' not in lot_ids

    def test_null_bop_returns_empty_rows(self):
        """A start lot with null BOP yields zero rows, no exception."""
        wip = _df(
            _make_wip_df(LOTID='LOT-NULL-BOP', SPECNAME='晶片切割-END',
                         BOP=None, PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-A'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF='PKG-A'),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        assert result == []


# ---------------------------------------------------------------------------
# Condition (a)+(c): BOP='U' zone depends on the waiting lot's own region
# ---------------------------------------------------------------------------

class TestBopURegionZone:
    """BOP[0]='U': allowed zone depends on the waiting lot's PJ_PRODUCEREGION."""

    def _wip(self, region, eqp_location, spec='Eutectic D/B', package='PKG-U'):
        return _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION=region, PACKAGE_LEF=package),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME=spec, STATUS='ACTIVE',
                         EQUIPMENTS='EQ-U', PACKAGE_LEF=package),
        ), [_resource('EQ-U', location=eqp_location)]

    def test_region_a_dong_allows_zone_abc(self):
        """PJ_PRODUCEREGION='A棟' → equipment at 焊接B區 (within A/B/C) matches."""
        wip, resources = self._wip('A棟', '焊接B區')
        result = _run_queue(wip, resources=resources)
        assert len(result) == 1
        assert result[0]['equipment'] == 'EQ-U'
        assert result[0]['matchSource'] == 'bop-package-zone'
        assert result[0]['equipmentSource'] == 'live'

    def test_region_d_qu_allows_only_zone_d(self):
        """PJ_PRODUCEREGION='D區' → equipment at 焊接D區 matches."""
        wip, resources = self._wip('D區', '焊接D區')
        result = _run_queue(wip, resources=resources)
        assert len(result) == 1
        assert result[0]['equipment'] == 'EQ-U'

    def test_region_d_qu_rejects_zone_a(self):
        """PJ_PRODUCEREGION='D區' → equipment at 焊接A區 does NOT match."""
        wip, resources = self._wip('D區', '焊接A區')
        result = _run_queue(wip, resources=resources)
        assert result == []

    @pytest.mark.parametrize('region', ['E區', None, 'X-unknown-region'])
    def test_other_regions_yield_zero_candidates(self, region):
        """Any region other than A棟/D區 (incl. 'E區', None, unknown) → zero rows."""
        wip, resources = self._wip(region, '焊接A區')
        result = _run_queue(wip, resources=resources)
        assert result == []


# ---------------------------------------------------------------------------
# Condition (c): BOP='E'/'P' fixed zones (independent of the lot's own region)
# ---------------------------------------------------------------------------

class TestBopFixedZones:
    """BOP[0]='E'/'P': allowed zone is FIXED, regardless of the waiting lot's
    own PJ_PRODUCEREGION."""

    def test_bop_e_fixed_zone_d_matches_regardless_of_lot_region(self):
        """BOP='E', lot region='A棟' (would allow A/B/C under U-rules) — but
        equipment at 焊接D區 (the FIXED zone for E) still matches."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='E-epoxy', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-E'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Epoxy D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-EPOXY', PACKAGE_LEF='PKG-E'),
        )
        resources = [_resource('EQ-EPOXY', location='焊接D區')]
        result = _run_queue(wip, resources=resources)
        assert len(result) == 1
        assert result[0]['equipment'] == 'EQ-EPOXY'
        assert result[0]['targetSpec'] == 'Epoxy D/B'

    def test_bop_e_rejects_wrong_zone(self):
        """BOP='E' equipment located outside 焊接D區 does NOT match."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='E-epoxy', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-E'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Epoxy D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-EPOXY', PACKAGE_LEF='PKG-E'),
        )
        resources = [_resource('EQ-EPOXY', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        assert result == []

    def test_bop_p_fixed_zone_e_matches_regardless_of_lot_region(self):
        """BOP='P', lot region=None — equipment at 焊接E區 (FIXED for P) matches."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='P-paste', PJ_PRODUCEREGION=None, PACKAGE_LEF='PKG-P'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='DBCB', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-DBCB', PACKAGE_LEF='PKG-P'),
        )
        resources = [_resource('EQ-DBCB', location='焊接E區')]
        result = _run_queue(wip, resources=resources)
        assert len(result) == 1
        assert result[0]['equipment'] == 'EQ-DBCB'

    def test_bop_p_rejects_wrong_zone(self):
        """BOP='P' equipment located outside 焊接E區 does NOT match."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='P-paste', PJ_PRODUCEREGION=None, PACKAGE_LEF='PKG-P'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='DBCB', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-DBCB', PACKAGE_LEF='PKG-P'),
        )
        resources = [_resource('EQ-DBCB', location='焊接D區')]
        result = _run_queue(wip, resources=resources)
        assert result == []


# ---------------------------------------------------------------------------
# Unknown/null BOP prefix
# ---------------------------------------------------------------------------

class TestUnknownBop:
    def test_unknown_bop_prefix_zero_rows(self):
        """BOP[0] not in U/E/P → zero rows, no error."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='X-unknown', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-A'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='1DB', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-1DB', PACKAGE_LEF='PKG-A'),
        )
        resources = [_resource('EQ-1DB', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        assert result == []

    def test_no_match_source_none_is_ever_emitted(self):
        """matchSource='none' is never included in output (unmatched lots emit
        zero rows, not a 'none'-tagged row)."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='Z-other', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-A'),
        )
        result = _run_queue(wip)
        none_rows = [r for r in result if r.get('matchSource') == 'none']
        assert none_rows == []
        assert result == []


# ---------------------------------------------------------------------------
# Condition (b): PACKAGE equality
# ---------------------------------------------------------------------------

class TestPackageMatch:
    def test_package_mismatch_no_candidate(self):
        """BOP/spec/zone all valid, but PACKAGE differs → zero candidates."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-WAIT'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF='PKG-DIFFERENT'),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        assert result == []

    def test_null_package_no_candidate(self):
        """Start lot with PACKAGE_LEF=None never matches (rule (b) requires equality)."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF=None),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF=None),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        assert result == []


# ---------------------------------------------------------------------------
# Idle-equipment history fallback (equipmentSource='history')
# ---------------------------------------------------------------------------

class TestIdleEquipmentHistoryFallback:
    def test_idle_equipment_matches_via_history(self):
        """Equipment with no live WIP row, resolved via LOTWIPHISTORY, is
        included as a candidate with equipmentSource='history'."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-B'),
        )
        resources = [_resource('EQ-IDLE', workcenter='焊接_DB', location='焊接A區')]
        idle_df = _idle_history_df(
            EQUIPMENTNAME='EQ-IDLE', SPECNAME='Eutectic D/B', PACKAGE_LF='PKG-B',
        )
        result = _run_queue(wip, resources=resources, idle_history_df=idle_df)
        assert len(result) == 1
        row = result[0]
        assert row['equipment'] == 'EQ-IDLE'
        assert row['equipmentSource'] == 'history'
        assert row['matchSource'] == 'bop-package-zone'
        assert row['targetSpec'] == 'Eutectic D/B'
        assert row['eqpPackageLef'] == 'PKG-B'

    def test_idle_equipment_no_history_data_yields_no_candidate(self):
        """Idle equipment with no matching LOTWIPHISTORY rows produces zero
        candidates, no exception."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-B'),
        )
        resources = [_resource('EQ-IDLE', workcenter='焊接_DB', location='焊接A區')]
        result = _run_queue(wip, resources=resources, idle_history_df=None)
        assert result == []

    def test_idle_equipment_history_spec_not_in_allowed_group(self):
        """Idle equipment's most-recent SPECNAME not in BOP-allowed group →
        excluded even though package/zone match."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-B'),
        )
        resources = [_resource('EQ-IDLE', workcenter='焊接_DB', location='焊接A區')]
        # DBCB is in the 'P' group, not 'U' — should not match a BOP='U' lot.
        idle_df = _idle_history_df(
            EQUIPMENTNAME='EQ-IDLE', SPECNAME='DBCB', PACKAGE_LF='PKG-B',
        )
        result = _run_queue(wip, resources=resources, idle_history_df=idle_df)
        assert result == []

    def test_idle_equipment_history_package_mismatch(self):
        """Idle equipment's most-recent PACKAGE_LF differs from the waiting
        lot's PACKAGE_LEF → excluded."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-B'),
        )
        resources = [_resource('EQ-IDLE', workcenter='焊接_DB', location='焊接A區')]
        idle_df = _idle_history_df(
            EQUIPMENTNAME='EQ-IDLE', SPECNAME='Eutectic D/B', PACKAGE_LF='PKG-OTHER',
        )
        result = _run_queue(wip, resources=resources, idle_history_df=idle_df)
        assert result == []

    def test_idle_equipment_wrong_zone_excluded(self):
        """Idle equipment located outside the BOP-allowed zone → excluded even
        with matching history spec/package."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='D區', PACKAGE_LEF='PKG-B'),
        )
        # D區 lot only allows 焊接D區; this idle equipment is in 焊接A區.
        resources = [_resource('EQ-IDLE', workcenter='焊接_DB', location='焊接A區')]
        idle_df = _idle_history_df(
            EQUIPMENTNAME='EQ-IDLE', SPECNAME='Eutectic D/B', PACKAGE_LF='PKG-B',
        )
        result = _run_queue(wip, resources=resources, idle_history_df=idle_df)
        assert result == []

    def test_active_equipment_excluded_from_idle_universe(self):
        """An equipment already in the live DB-02 pool is never also queried
        as an idle candidate (no duplicate 'live' + 'history' rows), and the
        idle-history Oracle query is skipped entirely when there is nothing
        idle to resolve."""
        wip = _df(
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-B'),
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-ACTIVE', PACKAGE_LEF='PKG-B'),
        )
        # EQ-ACTIVE is both live (has a WIP row) AND listed in the 焊接_DB
        # resource universe — it must NOT be treated as idle.
        resources = [_resource('EQ-ACTIVE', workcenter='焊接_DB', location='焊接A區')]
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=wip,
        ), patch(
            'mes_dashboard.services.resource_cache.get_all_resources',
            return_value=resources,
        ), patch(
            'mes_dashboard.services.db_scheduling_service.read_sql_df',
        ) as mock_read_sql:
            result = get_db_scheduling_queue()

        assert len(result) == 1
        assert result[0]['equipmentSource'] == 'live'
        # No idle equipment left to resolve → the history fallback query never runs.
        mock_read_sql.assert_not_called()


# ---------------------------------------------------------------------------
# DB-04: Sort order NULLS LAST (unchanged rule; fixtures updated for the new
# match model)
# ---------------------------------------------------------------------------

class TestSortOrder:
    """DB-04: sort PACKAGE_LEF → PJ_TYPE → WAFERLOT → UTS, NULLS LAST."""

    def test_sort_order_nulls_last(self):
        """Null PJ_TYPE/WAFERLOT/UTS sort-key values appear after non-null
        values (PACKAGE_LEF itself can never be null — rule (b) excludes it)."""
        wip = _df(
            _make_wip_df(LOTID='RUN1', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF='PKG-COMMON'),
            _make_wip_df(LOTID='LOT-FULL', SPECNAME='晶片切割-END',
                         PACKAGE_LEF='PKG-COMMON', PJ_TYPE='TypeA',
                         WAFERLOT='WL-A', UTS='2026/01/01',
                         BOP='U-test', PJ_PRODUCEREGION='A棟'),
            _make_wip_df(LOTID='LOT-NULLISH', SPECNAME='晶片切割-END',
                         PACKAGE_LEF='PKG-COMMON', PJ_TYPE=None,
                         WAFERLOT=None, UTS=None,
                         BOP='U-test', PJ_PRODUCEREGION='A棟'),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)

        assert len(result) == 2
        full_idx = next(i for i, r in enumerate(result) if r['lotId'] == 'LOT-FULL')
        null_idx = next(i for i, r in enumerate(result) if r['lotId'] == 'LOT-NULLISH')
        assert full_idx < null_idx

    def test_sort_primary_key_is_package_lef(self):
        """PACKAGE_LEF is the first sort key (ASC)."""
        wip = _df(
            _make_wip_df(LOTID='RUN-A', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-A', PACKAGE_LEF='AA-FIRST'),
            _make_wip_df(LOTID='RUN-B', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-B', PACKAGE_LEF='ZZ-LAST'),
            _make_wip_df(LOTID='LOT-B', SPECNAME='晶片切割-END',
                         PACKAGE_LEF='ZZ-LAST', BOP='U-test', PJ_PRODUCEREGION='A棟'),
            _make_wip_df(LOTID='LOT-A', SPECNAME='晶片切割-END',
                         PACKAGE_LEF='AA-FIRST', BOP='U-test', PJ_PRODUCEREGION='A棟'),
        )
        resources = [_resource('EQ-A', location='焊接A區'), _resource('EQ-B', location='焊接A區')]
        result = _run_queue(wip, resources=resources)

        lot_ids = [r['lotId'] for r in result]
        assert lot_ids.index('LOT-A') < lot_ids.index('LOT-B')


# ---------------------------------------------------------------------------
# Cache-miss fallback path
# ---------------------------------------------------------------------------

class TestCacheMissFallback:
    """Service must not 500 when get_cached_wip_data() returns None."""

    def test_cache_miss_returns_empty_list(self):
        """When cache returns None and Oracle fallback also fails, result is []."""
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=None,
        ), patch(
            'mes_dashboard.services.db_scheduling_service.read_sql_df',
            return_value=None,
        ), patch(
            'mes_dashboard.services.resource_cache.get_all_resources',
            return_value=[],
        ):
            result = get_db_scheduling_queue()
        assert result == []

    def test_cache_miss_with_oracle_fallback_returns_data(self):
        """When cache misses, Oracle fallback is attempted and a list is returned."""
        oracle_df = _df(
            _make_wip_df(LOTID='RUN-LOT', SPECNAME='Eutectic D/B', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-FBK', PACKAGE_LEF='PKG-FBK'),
            _make_wip_df(LOTID='START-LOT', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-FBK'),
        )
        with patch(
            'mes_dashboard.services.db_scheduling_service.get_cached_wip_data',
            return_value=None,
        ), patch(
            'mes_dashboard.services.db_scheduling_service.read_sql_df',
            return_value=oracle_df,
        ), patch(
            'mes_dashboard.services.resource_cache.get_all_resources',
            return_value=[],
        ):
            result = get_db_scheduling_queue()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Row shape / field names
# ---------------------------------------------------------------------------

class TestRowShape:
    """Each output row has the 16 required fields per §3.22 (2026-07 adds
    'equipmentSource')."""

    REQUIRED_FIELDS = {
        # Waiting lot
        'lotId', 'workflowName', 'packageLef', 'pjType', 'waferLot',
        'uts', 'qty', 'bop',
        # Candidate equipment's current/most-recent lot attributes
        'eqpPackageLef', 'eqpPjType', 'eqpWaferLot', 'eqpUts',
        # Dispatch metadata
        'targetSpec', 'equipment', 'matchSource', 'equipmentSource',
    }

    def test_row_has_all_required_fields(self):
        wip = _df(
            _make_wip_df(LOTID='START', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-A'),
            _make_wip_df(LOTID='RUN', SPECNAME='1DB', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF='PKG-A'),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        assert len(result) >= 1
        for row in result:
            assert self.REQUIRED_FIELDS <= set(row.keys()), (
                f"Row missing fields: {self.REQUIRED_FIELDS - set(row.keys())}"
            )

    def test_eqp_fields_come_from_running_lot_not_start_lot(self):
        """eqpPjType/eqpWaferLot/eqpUts reflect the equipment's running lot,
        not the waiting start lot. eqpPackageLef necessarily equals
        packageLef now (rule (b) requires PACKAGE equality to match at all)."""
        wip = _df(
            _make_wip_df(LOTID='START', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟',
                         PACKAGE_LEF='PKG-X', PJ_TYPE='WAIT-PJ',
                         WAFERLOT='WAIT-WL', UTS='2026/01/01'),
            _make_wip_df(LOTID='RUN', SPECNAME='1DB', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF='PKG-X',
                         PJ_TYPE='RUN-PJ', WAFERLOT='RUN-WL', UTS='2026/06/01'),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        assert len(result) == 1
        row = result[0]
        assert row['packageLef'] == 'PKG-X'
        assert row['pjType'] == 'WAIT-PJ'
        assert row['eqpPackageLef'] == 'PKG-X'
        assert row['eqpPjType'] == 'RUN-PJ'
        assert row['eqpWaferLot'] == 'RUN-WL'
        assert row['eqpUts'] == '2026/06/01'
        assert row['equipmentSource'] == 'live'

    def test_qty_is_integer(self):
        wip = _df(
            _make_wip_df(LOTID='START', SPECNAME='晶片切割-END',
                         BOP='U-test', PJ_PRODUCEREGION='A棟', PACKAGE_LEF='PKG-A', QTY=50),
            _make_wip_df(LOTID='RUN', SPECNAME='1DB', STATUS='ACTIVE',
                         EQUIPMENTS='EQ-001', PACKAGE_LEF='PKG-A'),
        )
        resources = [_resource('EQ-001', location='焊接A區')]
        result = _run_queue(wip, resources=resources)
        for row in result:
            assert isinstance(row['qty'], int)
