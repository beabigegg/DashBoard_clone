# -*- coding: utf-8 -*-
"""Unit tests for LineageEngine."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from mes_dashboard.services.lineage_engine import LineageEngine


@patch("mes_dashboard.services.lineage_engine.read_sql_df")
def test_resolve_split_ancestors_batches_and_enforces_max_depth(mock_read_sql_df):
    cids = [f"C{i:04d}" for i in range(1001)]
    mock_read_sql_df.side_effect = [
        pd.DataFrame(
            [
                {
                    "CONTAINERID": "C0000",
                    "SPLITFROMID": "P0000",
                    "CONTAINERNAME": "LOT-0000",
                    "SPLIT_DEPTH": 1,
                },
                {
                    "CONTAINERID": "P0000",
                    "SPLITFROMID": None,
                    "CONTAINERNAME": "LOT-P0000",
                    "SPLIT_DEPTH": 2,
                },
            ]
        ),
        pd.DataFrame(
            [
                {
                    "CONTAINERID": "C1000",
                    "SPLITFROMID": "P1000",
                    "CONTAINERNAME": "LOT-1000",
                    "SPLIT_DEPTH": 1,
                },
                {
                    "CONTAINERID": "C-TOO-DEEP",
                    "SPLITFROMID": "P-TOO-DEEP",
                    "CONTAINERNAME": "LOT-DEEP",
                    "SPLIT_DEPTH": 21,
                },
            ]
        ),
    ]

    result = LineageEngine.resolve_split_ancestors(cids, {"INIT": "LOT-INIT"})

    assert mock_read_sql_df.call_count == 2
    first_sql, first_params = mock_read_sql_df.call_args_list[0].args
    second_sql, second_params = mock_read_sql_df.call_args_list[1].args
    assert "LEVEL <= 20" in first_sql
    assert "LEVEL <= 20" in second_sql
    assert len(first_params) == 1000
    assert len(second_params) == 1

    assert result["child_to_parent"]["C0000"] == "P0000"
    assert result["child_to_parent"]["C1000"] == "P1000"
    assert "C-TOO-DEEP" not in result["child_to_parent"]
    assert result["cid_to_name"]["C0000"] == "LOT-0000"
    assert result["cid_to_name"]["INIT"] == "LOT-INIT"


@patch("mes_dashboard.services.lineage_engine.read_sql_df")
def test_resolve_merge_sources_batches_and_returns_mapping(mock_read_sql_df):
    target_cids = [f"T{i:04d}" for i in range(1001)]
    mock_read_sql_df.side_effect = [
        pd.DataFrame(
            [
                {"FINISHED_CID": "T0000", "SOURCE_CID": "SRC-A"},
                {"FINISHED_CID": "T0000", "SOURCE_CID": "SRC-B"},
            ]
        ),
        pd.DataFrame(
            [
                {"FINISHED_CID": "T1000", "SOURCE_CID": "SRC-C"},
                {"FINISHED_CID": "T1000", "SOURCE_CID": "SRC-C"},
                {"FINISHED_CID": None, "SOURCE_CID": "SRC-INVALID"},
            ]
        ),
    ]

    result = LineageEngine.resolve_merge_sources(target_cids)

    assert mock_read_sql_df.call_count == 2
    first_sql, first_params = mock_read_sql_df.call_args_list[0].args
    second_sql, second_params = mock_read_sql_df.call_args_list[1].args
    assert "{{ TARGET_CID_FILTER }}" not in first_sql
    assert "{{ TARGET_CID_FILTER }}" not in second_sql
    assert len(first_params) == 1000
    assert len(second_params) == 1

    assert result["T0000"] == ["SRC-A", "SRC-B"]
    assert result["T1000"] == ["SRC-C"]


@patch("mes_dashboard.services.lineage_engine.LineageEngine.resolve_merge_sources")
@patch("mes_dashboard.services.lineage_engine.LineageEngine.resolve_split_ancestors")
def test_resolve_full_genealogy_combines_split_and_merge(
    mock_resolve_split_ancestors,
    mock_resolve_merge_sources,
):
    mock_resolve_split_ancestors.side_effect = [
        {
            "child_to_parent": {
                "A": "B",
                "B": "C",
            },
            "cid_to_name": {
                "A": "LOT-A",
                "B": "LOT-B",
                "C": "LOT-C",
            },
        },
        {
            "child_to_parent": {
                "M1": "M0",
            },
            "cid_to_name": {
                "M1": "LOT-M1",
                "M0": "LOT-M0",
            },
        },
    ]
    mock_resolve_merge_sources.return_value = {"B": ["M1"]}

    result = LineageEngine.resolve_full_genealogy(["A"], {"A": "LOT-A"})

    assert result["ancestors"] == {"A": {"B", "C", "M1", "M0"}}
    assert result["cid_to_name"]["A"] == "LOT-A"
    assert result["cid_to_name"]["M0"] == "LOT-M0"

    # parent_map should have direct edges only
    pm = result["parent_map"]
    assert pm["A"] == ["B"]
    assert pm["B"] == ["C", "M1"] or set(pm["B"]) == {"C", "M1"}
    assert pm["M1"] == ["M0"]

    # merge_edges: B → M1 (LOT-B matched merge source)
    me = result["merge_edges"]
    assert "M1" in me.get("B", [])

    assert mock_resolve_split_ancestors.call_count == 2
    mock_resolve_merge_sources.assert_called_once()


@patch("mes_dashboard.services.lineage_engine.read_sql_df")
def test_split_ancestors_matches_legacy_bfs_for_five_known_lots(mock_read_sql_df):
    parent_by_cid = {
        "L1": "L1P1",
        "L1P1": "L1P2",
        "L2": "L2P1",
        "L3": None,
        "L4": "L4P1",
        "L4P1": "L4P2",
        "L4P2": "L4P3",
        "L5": "L5P1",
        "L5P1": "L5P2",
        "L5P2": "L5P1",
    }
    name_by_cid = {
        "L1": "LOT-1",
        "L1P1": "LOT-1-P1",
        "L1P2": "LOT-1-P2",
        "L2": "LOT-2",
        "L2P1": "LOT-2-P1",
        "L3": "LOT-3",
        "L4": "LOT-4",
        "L4P1": "LOT-4-P1",
        "L4P2": "LOT-4-P2",
        "L4P3": "LOT-4-P3",
        "L5": "LOT-5",
        "L5P1": "LOT-5-P1",
        "L5P2": "LOT-5-P2",
    }
    seed_lots = ["L1", "L2", "L3", "L4", "L5"]

    def _connect_by_rows(start_cids):
        rows = []
        for seed in start_cids:
            current = seed
            depth = 1
            visited = set()
            while current and depth <= 20 and current not in visited:
                visited.add(current)
                rows.append(
                    {
                        "CONTAINERID": current,
                        "SPLITFROMID": parent_by_cid.get(current),
                        "CONTAINERNAME": name_by_cid.get(current),
                        "SPLIT_DEPTH": depth,
                    }
                )
                current = parent_by_cid.get(current)
                depth += 1
        return pd.DataFrame(rows)

    def _mock_read_sql(_sql, params, **kwargs):
        requested = [value for value in params.values()]
        return _connect_by_rows(requested)

    mock_read_sql_df.side_effect = _mock_read_sql

    connect_by_result = LineageEngine.resolve_split_ancestors(seed_lots)

    # Legacy BFS reference implementation from previous mid_section_defect_service.
    legacy_child_to_parent = {}
    legacy_cid_to_name = {}
    frontier = list(seed_lots)
    seen = set(seed_lots)
    rounds = 0
    while frontier:
        rounds += 1
        batch_rows = []
        for cid in frontier:
            batch_rows.append(
                {
                    "CONTAINERID": cid,
                    "SPLITFROMID": parent_by_cid.get(cid),
                    "CONTAINERNAME": name_by_cid.get(cid),
                }
            )
        new_parents = set()
        for row in batch_rows:
            cid = row["CONTAINERID"]
            split_from = row["SPLITFROMID"]
            name = row["CONTAINERNAME"]
            if isinstance(name, str) and name:
                legacy_cid_to_name[cid] = name
            if isinstance(split_from, str) and split_from and split_from != cid:
                legacy_child_to_parent[cid] = split_from
                if split_from not in seen:
                    seen.add(split_from)
                    new_parents.add(split_from)
        frontier = list(new_parents)
        if rounds > 20:
            break

    assert connect_by_result["child_to_parent"] == legacy_child_to_parent
    assert connect_by_result["cid_to_name"] == legacy_cid_to_name


@patch("mes_dashboard.services.lineage_engine.LineageEngine._build_semantic_links")
@patch("mes_dashboard.services.lineage_engine.LineageEngine._resolve_container_snapshot")
@patch("mes_dashboard.services.lineage_engine.LineageEngine.resolve_merge_sources")
@patch("mes_dashboard.services.lineage_engine.LineageEngine.resolve_split_ancestors")
def test_resolve_full_genealogy_includes_semantic_edges(
    mock_resolve_split_ancestors,
    mock_resolve_merge_sources,
    mock_resolve_container_snapshot,
    mock_build_semantic_links,
):
    mock_resolve_split_ancestors.return_value = {
        "child_to_parent": {"GD-LOT": "SRC-LOT"},
        "cid_to_name": {
            "GD-LOT": "GD25060502-A11",
            "SRC-LOT": "56014S00T-5K07R",
        },
    }
    mock_resolve_merge_sources.return_value = {}
    snapshots = {
        "GD-LOT": {
            "CONTAINERID": "GD-LOT",
            "CONTAINERNAME": "GD25060502-A11",
            "MFGORDERNAME": "GD25060502",
            "OBJECTTYPE": "LOT",
            "FIRSTNAME": "56014S00T-5K07R",
            "ORIGINALCONTAINERID": "SRC-LOT",
            "SPLITFROMID": "SRC-LOT",
        },
        "SRC-LOT": {
            "CONTAINERID": "SRC-LOT",
            "CONTAINERNAME": "56014S00T-5K07R",
            "MFGORDERNAME": None,
            "OBJECTTYPE": "LOT",
            "FIRSTNAME": "56014S00T-5K07R",
            "ORIGINALCONTAINERID": None,
            "SPLITFROMID": None,
        },
        "WAFER-LOT": {
            "CONTAINERID": "WAFER-LOT",
            "CONTAINERNAME": "56014S00T-5K07R",
            "MFGORDERNAME": None,
            "OBJECTTYPE": "LOT",
            "FIRSTNAME": "56014S00T-5K07R",
            "ORIGINALCONTAINERID": None,
            "SPLITFROMID": None,
        },
    }
    mock_resolve_container_snapshot.return_value = snapshots
    mock_build_semantic_links.return_value = (
        snapshots,
        [
            ("WAFER-LOT", "GD-LOT", "wafer_origin"),
            ("SRC-LOT", "GD-LOT", "gd_rework_source"),
        ],
        {"WAFER-LOT"},
    )

    result = LineageEngine.resolve_full_genealogy(["GD-LOT"], {"GD-LOT": "GD25060502-A11"})

    assert "GD-LOT" in result["parent_map"]
    assert "SRC-LOT" in result["parent_map"]["GD-LOT"]
    assert "WAFER-LOT" in result["parent_map"]["GD-LOT"]
    edge_types = {edge["edge_type"] for edge in result["edges"]}
    assert "wafer_origin" in edge_types
    assert "gd_rework_source" in edge_types


def test_lineage_engine_uses_slow_connection():
    """Regression: lineage_engine must use read_sql_df_slow (non-pooled)."""
    import mes_dashboard.services.lineage_engine as le
    from mes_dashboard.core.database import read_sql_df_slow

    assert le.read_sql_df is read_sql_df_slow
