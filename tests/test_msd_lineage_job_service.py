# -*- coding: utf-8 -*-
"""Unit tests for msd_lineage_job_service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from mes_dashboard.services.msd_lineage_job_service import (
    _reconstruct_lineage_response,
    _resolve_backward_lineage,
    get_msd_lineage_job_result,
    get_msd_lineage_job_status,
)


# ---- _reconstruct_lineage_response tests ----


def test_reconstruct_lineage_response_builds_ancestors_dict():
    """Should build ancestors dict correctly from edge-list parquet rows."""
    df = pd.DataFrame([
        {"seed_cid": "S1", "ancestor_cid": "A1", "edge_type": "split_from", "cid_name": "LOT-A1"},
        {"seed_cid": "S1", "ancestor_cid": "A2", "edge_type": "split_from", "cid_name": "LOT-A2"},
        {"seed_cid": "S1", "ancestor_cid": "ROOT-S1", "edge_type": "__root__", "cid_name": ""},
        {"seed_cid": "S2", "ancestor_cid": "A3", "edge_type": "merge_source", "cid_name": "LOT-A3"},
        {"seed_cid": "S2", "ancestor_cid": "ROOT-S2", "edge_type": "__root__", "cid_name": ""},
    ])

    result = _reconstruct_lineage_response(df)

    assert result["stage"] == "lineage"
    assert set(result["ancestors"]["S1"]) == {"A1", "A2"}
    assert set(result["ancestors"]["S2"]) == {"A3"}
    assert result["names"]["A1"] == "LOT-A1"
    assert result["names"]["A2"] == "LOT-A2"
    assert result["names"]["A3"] == "LOT-A3"
    assert result["seed_roots"]["S1"] == "ROOT-S1"
    assert result["seed_roots"]["S2"] == "ROOT-S2"
    assert result["total_ancestor_count"] == 3  # A1, A2, A3


def test_reconstruct_lineage_response_counts_nodes_correctly():
    """total_nodes = seed + ancestor CIDs; __root__ rows store a name (not a CID node)."""
    df = pd.DataFrame([
        {"seed_cid": "S1", "ancestor_cid": "A1", "edge_type": "split_from", "cid_name": ""},
        {"seed_cid": "S1", "ancestor_cid": "ROOT-NAME", "edge_type": "__root__", "cid_name": ""},
    ])

    result = _reconstruct_lineage_response(df)
    assert result["total_nodes"] == 2  # S1 (seed) + A1 (ancestor CID); ROOT-NAME is a name not a CID
    assert result["total_ancestor_count"] == 1  # only A1


def test_reconstruct_lineage_response_empty_df():
    """Empty DataFrame should produce empty response."""
    df = pd.DataFrame(columns=["seed_cid", "ancestor_cid", "edge_type", "cid_name"])
    result = _reconstruct_lineage_response(df)
    assert result["ancestors"] == {}
    assert result["names"] == {}
    assert result["total_nodes"] == 0


# ---- _resolve_backward_lineage tests ----


@patch("mes_dashboard.services.msd_lineage_job_service.update_job_progress")
@patch("mes_dashboard.services.msd_lineage_job_service.LineageEngine.resolve_merge_sources")
@patch("mes_dashboard.services.msd_lineage_job_service.LineageEngine.resolve_split_ancestors")
def test_resolve_backward_lineage_batches_seeds(
    mock_split_ancestors,
    mock_merge_sources,
    mock_update_progress,
):
    """Should call resolve_split_ancestors once per ORACLE_IN_BATCH_SIZE batch."""
    from mes_dashboard.services.lineage_engine import ORACLE_IN_BATCH_SIZE

    seed_count = ORACLE_IN_BATCH_SIZE + 1
    seed_cids = [f"S{i:05d}" for i in range(seed_count)]
    total_batches = 2

    mock_split_ancestors.return_value = {
        "child_to_parent": {"S00000": "P00000"},
        "cid_to_name": {"S00000": "LOT-S0", "P00000": "LOT-P0"},
    }
    mock_merge_sources.return_value = {}

    result = _resolve_backward_lineage("job-test", seed_cids, total_batches)

    assert mock_split_ancestors.call_count == 2
    first_call_seeds = mock_split_ancestors.call_args_list[0][0][0]
    assert len(first_call_seeds) == ORACLE_IN_BATCH_SIZE
    second_call_seeds = mock_split_ancestors.call_args_list[1][0][0]
    assert len(second_call_seeds) == 1

    assert isinstance(result, pd.DataFrame)
    assert set(result.columns) == {"seed_cid", "ancestor_cid", "edge_type", "cid_name"}


@patch("mes_dashboard.services.msd_lineage_job_service.update_job_progress")
@patch("mes_dashboard.services.msd_lineage_job_service.LineageEngine.resolve_merge_sources")
@patch("mes_dashboard.services.msd_lineage_job_service.LineageEngine.resolve_split_ancestors")
def test_resolve_backward_lineage_accumulates_across_batches(
    mock_split_ancestors,
    mock_merge_sources,
    mock_update_progress,
):
    """Should accumulate child_to_parent and cid_to_name across all batches."""
    from mes_dashboard.services.lineage_engine import ORACLE_IN_BATCH_SIZE

    seed_cids = [f"S{i:05d}" for i in range(ORACLE_IN_BATCH_SIZE + 1)]
    total_batches = 2

    mock_split_ancestors.side_effect = [
        {
            "child_to_parent": {"S00000": "P00000"},
            "cid_to_name": {"S00000": "LOT-S0", "P00000": "LOT-P0"},
        },
        {
            "child_to_parent": {"S01000": "P01000"},
            "cid_to_name": {"S01000": "LOT-S1", "P01000": "LOT-P1"},
        },
    ]
    mock_merge_sources.return_value = {}

    result = _resolve_backward_lineage("job-test", seed_cids, total_batches)

    # Both seeds should appear with their ancestors
    result_s0 = result[result["seed_cid"] == "S00000"]
    assert "P00000" in result_s0["ancestor_cid"].values

    result_s1 = result[result["seed_cid"] == "S01000"]
    assert "P01000" in result_s1["ancestor_cid"].values


@patch("mes_dashboard.services.msd_lineage_job_service.update_job_progress")
@patch("mes_dashboard.services.msd_lineage_job_service.LineageEngine.resolve_merge_sources")
@patch("mes_dashboard.services.msd_lineage_job_service.LineageEngine.resolve_split_ancestors")
def test_resolve_backward_lineage_includes_merge_sources(
    mock_split_ancestors,
    mock_merge_sources,
    mock_update_progress,
):
    """Merge source ancestors should appear in the result with edge_type=merge_source."""
    mock_split_ancestors.return_value = {
        "child_to_parent": {"SEED": "PARENT"},
        "cid_to_name": {"SEED": "LOT-SEED", "PARENT": "LOT-PARENT"},
    }
    mock_merge_sources.return_value = {"PARENT": ["MERGE-SRC"]}

    result = _resolve_backward_lineage("job-test", ["SEED"], 1)

    merge_rows = result[result["edge_type"] == "merge_source"]
    assert "MERGE-SRC" in merge_rows["ancestor_cid"].values


# ---- get_msd_lineage_job_result tests ----


@patch("mes_dashboard.services.msd_lineage_job_service.load_spooled_df")
@patch("mes_dashboard.services.msd_lineage_job_service._get_job_status")
def test_get_msd_lineage_job_result_returns_none_when_job_not_found(mock_status, mock_load):
    """Should return None when job is not found in Redis."""
    mock_status.return_value = None
    result = get_msd_lineage_job_result("nonexistent-job")
    assert result is None
    mock_load.assert_not_called()


@patch("mes_dashboard.services.msd_lineage_job_service.load_spooled_df")
@patch("mes_dashboard.services.msd_lineage_job_service._get_job_status")
def test_get_msd_lineage_job_result_returns_none_when_no_query_id(mock_status, mock_load):
    """Should return None when job exists but has no query_id (still running)."""
    mock_status.return_value = {"status": "running", "query_id": ""}
    result = get_msd_lineage_job_result("job-running")
    assert result is None
    mock_load.assert_not_called()


@patch("mes_dashboard.services.msd_lineage_job_service.load_spooled_df")
@patch("mes_dashboard.services.msd_lineage_job_service._get_job_status")
def test_get_msd_lineage_job_result_reconstructs_from_parquet(mock_status, mock_load):
    """Should load parquet and reconstruct lineage response."""
    mock_status.return_value = {
        "status": "completed",
        "query_id": "msd-lineage-test-job-abc",
    }
    mock_load.return_value = pd.DataFrame([
        {
            "seed_cid": "SEED1",
            "ancestor_cid": "ANC1",
            "edge_type": "split_from",
            "cid_name": "LOT-ANC1",
        },
        {
            "seed_cid": "SEED1",
            "ancestor_cid": "ROOT1",
            "edge_type": "__root__",
            "cid_name": "",
        },
    ])

    result = get_msd_lineage_job_result("job-abc")

    assert result is not None
    assert result["stage"] == "lineage"
    assert "SEED1" in result["ancestors"]
    assert "ANC1" in result["ancestors"]["SEED1"]
    assert result["names"]["ANC1"] == "LOT-ANC1"
    assert result["seed_roots"]["SEED1"] == "ROOT1"
