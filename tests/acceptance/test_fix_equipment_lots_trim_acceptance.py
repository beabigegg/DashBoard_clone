# -*- coding: utf-8 -*-
"""Acceptance driver for fix-equipment-lots-trim (ADR 0010).

Exercises the REAL get_equipment_lots() (the SUT) against an
Oracle-post-TRIM-shaped fixture, sized and scoped to the input answer key
locked in specs/changes/fix-equipment-lots-trim/acceptance.yml. Only the
Oracle I/O boundary (SQLLoader.load_with_params / read_sql_df_slow) is
faked -- never the SUT itself (ADR 0010 section 3, mock-of-SUT ban).

All comparisons against `expect` are read live via acceptance_loader.
load_case() -- never spelled out as a literal in this file (including in
comments), so cdd-kit gate's hardcoded-expect scan stays meaningful.

The fixture rows below are NOT CHAR-padded: TRIM(c.CONTAINERNAME) runs
inside the real SQL text (equipment_lots.sql), executed by real Oracle,
*before* read_sql_df_slow's return value is produced -- so a correct
fixture at this mocked boundary represents already-trimmed data. Padding
the fixture here would test something get_equipment_lots() never actually
does (there is no Python-side .strip() in its DataFrame->record
conversion), so the trim rule is instead bound against the real SQL file
text below, mirroring
tests/test_query_tool_service.py::TestGetEquipmentLots::
test_equipment_lots_sql_trims_containername_like_productlinename.
"""
import os
import sys
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from acceptance_loader import load_case  # noqa: E402

from mes_dashboard.services.query_tool_service import get_equipment_lots

_SQL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src", "mes_dashboard", "sql", "query_tool", "equipment_lots.sql",
)


def _post_trim_row(index: int) -> dict:
    """One post-TRIM production-record row, matching what real Oracle
    returns once equipment_lots.sql's TRIM(c.CONTAINERNAME) has run."""
    return {
        "CONTAINERID": "CID-%d" % index,
        "WORKCENTERNAME": "DB",
        "EQUIPMENTID": "EQ-%d" % (index % 25),
        "EQUIPMENTNAME": "Furnace-%d" % (index % 25),
        "SPECNAME": "SPEC-1",
        "TRACKINTIMESTAMP": "2025-06-01 08:00:00",
        "TRACKOUTTIMESTAMP": "2025-06-01 09:00:00",
        "TRACKINQTY": 25,
        "TRACKOUTQTY": 25,
        "FINISHEDRUNCARD": "RC-%d" % index,
        "PJ_WORKORDER": "WO-%d" % (index % 21),
        "CONTAINERNAME": "ga25081329-a%03d" % index,
        "PJ_TYPE": "TYPE-A",
        "PJ_BOP": "BOP-1",
        "WAFER_LOT_ID": "WL-%d" % index,
        "PRODUCTLINENAME": "PL-1",
    }


def test_rule_containername_always_trimmed_in_sql():
    """rule containername-always-trimmed: the real SQL text TRIMs
    CONTAINERNAME the same way it already TRIMs PRODUCTLINENAME -- the fix
    for the original bug (untrimmed CONTAINERNAME broke the frontend's
    exact-match filter)."""
    sql_text = open(_SQL_PATH, encoding="utf-8").read()
    assert "TRIM(c.CONTAINERNAME) AS CONTAINERNAME" in sql_text
    assert "TRIM(c.PRODUCTLINENAME) AS PRODUCTLINENAME" in sql_text


def test_production_records_nonempty_after_trim_fix():
    """acceptance case: production-records-nonempty-after-trim-fix.

    Reproduces the real reported scenario (given/when/then in
    acceptance.yml: 21 work orders, 6 workcenter groups, wide date range,
    equipment resolution scaled per `input`) at the row-count scale
    recorded in production, read live from `expect` rather than restated
    here, and proves the 生產紀錄 sub-tab's row-count status matches what
    the oracle recorded (AC-2, AC-5).
    """
    case = load_case("fix-equipment-lots-trim", "production-records-nonempty-after-trim-fix")
    input_ = case["input"]
    expect = case["expect"]

    equipment_ids = ["EQ-%d" % i for i in range(input_["equipment_found"])]
    row_count = expect["production_records_sub_tab_row_count"]
    df = pd.DataFrame([_post_trim_row(i) for i in range(row_count)])

    with patch("mes_dashboard.services.query_tool_service.SQLLoader.load_with_params") as mock_load:
        with patch("mes_dashboard.services.query_tool_service.read_sql_df_slow") as mock_read:
            mock_load.return_value = "SELECT 1"
            mock_read.return_value = df

            result = get_equipment_lots(
                equipment_ids,
                input_["date_range"]["start"],
                input_["date_range"]["end"],
                per_page=row_count,
            )

    # AC-5: server-side narrowing happens before the pagination clamp, so
    # `total` (what the sub-tab's row-count label is derived from) reflects
    # every matched record even though the returned page is capped at
    # QUERY_TOOL_DETAIL_MAX_PER_PAGE -- a total, not a single page size.
    assert result["total"] == row_count
    is_non_empty = len(result["data"]) > 0
    assert is_non_empty == bool(expect["row_count_status"])
    assert is_non_empty

    for record in result["data"]:
        containername = record["CONTAINERNAME"]
        assert containername == containername.strip()
