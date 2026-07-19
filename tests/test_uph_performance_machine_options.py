# -*- coding: utf-8 -*-
"""Tests for uph_performance_machine_options (DW_MES_RESOURCE-backed cascadable
dropdown source for the redesigned UPH filter bar)."""
from unittest.mock import patch

import pandas as pd
import pytest


def _fake_df():
    return pd.DataFrame(
        [
            {"EQUIPMENT_ID": "GDBA-0131", "FAMILY": "GDBA", "MODEL": "DBA_AD838_EAP", "WORKCENTER": "焊接_DB"},
            {"EQUIPMENT_ID": "GDBA-0108", "FAMILY": "GDBA", "MODEL": "DBA_AD830", "WORKCENTER": "焊接_DB"},
            {"EQUIPMENT_ID": "GWBA-0192", "FAMILY": "GWBA", "MODEL": "WBA_iHawk Xtreme", "WORKCENTER": "焊接_WB"},
            # Non GDBA/GWBA rows must be dropped (defensive; SQL already scopes).
            {"EQUIPMENT_ID": "GPTA-0001", "FAMILY": "GPTA", "MODEL": "X", "WORKCENTER": "其他"},
        ]
    )


@pytest.fixture(autouse=True)
def _reset_cache():
    import mes_dashboard.services.uph_performance_machine_options as mod
    mod._cache = None
    mod._cache_ts = 0.0
    yield
    mod._cache = None
    mod._cache_ts = 0.0


def test_shapes_families_models_workcenters_equipment():
    from mes_dashboard.services.uph_performance_machine_options import get_machine_options

    with patch("mes_dashboard.core.database.read_sql_df_slow", return_value=_fake_df()):
        data = get_machine_options(force=True)

    # families: only GDBA/GWBA, labelled Die-Bond / Wire-Bond
    assert data["families"] == [
        {"code": "GDBA", "label": "Die-Bond"},
        {"code": "GWBA", "label": "Wire-Bond"},
    ]
    # equipment: GPTA row dropped; sorted by equipment_id
    eq_ids = [e["equipment_id"] for e in data["equipment"]]
    assert eq_ids == ["GDBA-0108", "GDBA-0131", "GWBA-0192"]
    assert "GPTA-0001" not in eq_ids
    # each equipment row carries family/model/workcenter for client-side cascade
    row = next(e for e in data["equipment"] if e["equipment_id"] == "GDBA-0131")
    assert row == {"equipment_id": "GDBA-0131", "family": "GDBA", "model": "DBA_AD838_EAP", "workcenter": "焊接_DB"}
    # models carry their family (so the frontend can cascade family -> model)
    assert {"family": "GDBA", "model": "DBA_AD838_EAP"} in data["models"]
    assert {"family": "GWBA", "model": "WBA_iHawk Xtreme"} in data["models"]
    assert all(m["family"] in ("GDBA", "GWBA") for m in data["models"])
    # workcenters: distinct, sorted, GPTA's '其他' excluded
    assert data["workcenters"] == ["焊接_DB", "焊接_WB"]


def test_caches_and_force_refreshes():
    from mes_dashboard.services.uph_performance_machine_options import get_machine_options

    with patch("mes_dashboard.core.database.read_sql_df_slow", return_value=_fake_df()) as m:
        get_machine_options(force=True)   # 1st query
        get_machine_options()             # cache hit -> no new query
        assert m.call_count == 1
        get_machine_options(force=True)   # force -> re-query
        assert m.call_count == 2
