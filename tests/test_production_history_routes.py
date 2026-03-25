# -*- coding: utf-8 -*-
"""Route tests for Production History APIs.

Coverage:
  - 400 validation: missing pj_types, missing dates, date range exceeded
  - 410 dataset expired: page/matrix/export with missing dataset_id
  - 503 overload: heavy_query_overloaded, memory_guard_rejected
  - Success envelope shape: query, page, matrix
  - Filter contract: /page and /matrix accept same {workcenter_group, spec, equipment_id}
  - Export query params match /page filter semantics
  - LOT trace: max-depth / cycle errors return 400
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from mes_dashboard.app import create_app


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ── 0. Contract: success envelope ────────────────────────────────────────────

@patch("mes_dashboard.routes.production_history_routes.query_production_history")
def test_query_success_envelope(mock_query, client):
    mock_query.return_value = {
        "dataset_id": "ph-abc123",
        "detail": {"rows": [], "pagination": {"page": 1, "per_page": 25, "total_rows": 0, "total_pages": 0}},
        "matrix": {"tree": [], "month_columns": []},
        "filter_options": {"pj_types": ["GA"]},
        "meta": {"ttl_seconds": 3600, "expires_at": 9999999999, "row_count": 0},
    }
    resp = client.post(
        "/api/production-history/query",
        json={"pj_types": ["GA"], "start_date": "2026-03-01", "end_date": "2026-03-10"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "dataset_id" in data["data"]
    assert "detail" in data["data"]
    assert "matrix" in data["data"]


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
@patch("mes_dashboard.routes.production_history_routes.compute_detail_page")
def test_page_success_envelope(mock_page, mock_spool, client):
    mock_spool.return_value = "/tmp/fake.parquet"
    mock_page.return_value = {
        "rows": [{"lot_id": "GA001"}],
        "pagination": {"page": 1, "per_page": 25, "total_rows": 1, "total_pages": 1},
    }
    resp = client.post(
        "/api/production-history/page",
        json={"dataset_id": "ph-abc123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "rows" in data["data"]
    assert "pagination" in data["data"]


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
@patch("mes_dashboard.routes.production_history_routes.compute_matrix_view")
def test_matrix_success_envelope(mock_matrix, mock_spool, client):
    mock_spool.return_value = "/tmp/fake.parquet"
    mock_matrix.return_value = {"tree": [], "month_columns": ["2026-03"]}
    resp = client.post(
        "/api/production-history/matrix",
        json={"dataset_id": "ph-abc123"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert "tree" in data["data"]
    assert "month_columns" in data["data"]


# ── 1. Validation: 400 ────────────────────────────────────────────────────────

def test_query_missing_pj_types(client):
    resp = client.post(
        "/api/production-history/query",
        json={"start_date": "2026-03-01", "end_date": "2026-03-10"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_query_missing_dates(client):
    resp = client.post(
        "/api/production-history/query",
        json={"pj_types": ["GA"]},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_query_empty_pj_types(client):
    resp = client.post(
        "/api/production-history/query",
        json={"pj_types": [], "start_date": "2026-03-01", "end_date": "2026-03-10"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


@patch("mes_dashboard.routes.production_history_routes.query_production_history")
def test_query_date_range_exceeded(mock_query, client):
    from mes_dashboard.services.production_history_service import MAX_DATE_RANGE_DAYS
    mock_query.side_effect = ValueError(f"日期區間超過上限 {MAX_DATE_RANGE_DAYS} 天")
    resp = client.post(
        "/api/production-history/query",
        json={"pj_types": ["GA"], "start_date": "2024-01-01", "end_date": "2026-03-25"},
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "VALIDATION_ERROR"


# ── 2. Dataset expired: 410 ───────────────────────────────────────────────────

def test_page_missing_dataset_id(client):
    resp = client.post("/api/production-history/page", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
def test_page_dataset_expired(mock_spool, client):
    mock_spool.return_value = None
    resp = client.post(
        "/api/production-history/page",
        json={"dataset_id": "ph-expired"},
    )
    assert resp.status_code == 410
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "CACHE_EXPIRED"


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
def test_matrix_dataset_expired(mock_spool, client):
    mock_spool.return_value = None
    resp = client.post(
        "/api/production-history/matrix",
        json={"dataset_id": "ph-expired"},
    )
    assert resp.status_code == 410
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "CACHE_EXPIRED"


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
def test_export_dataset_expired(mock_spool, client):
    mock_spool.return_value = None
    resp = client.get("/api/production-history/export?dataset_id=ph-expired")
    assert resp.status_code == 410
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"]["code"] == "CACHE_EXPIRED"


# ── 3. Overload: 503 + Retry-After ────────────────────────────────────────────

@patch("mes_dashboard.routes.production_history_routes.query_production_history")
def test_query_heavy_query_overloaded(mock_query, client):
    mock_query.side_effect = RuntimeError("heavy_query_overloaded")
    resp = client.post(
        "/api/production-history/query",
        json={"pj_types": ["GA"], "start_date": "2026-03-01", "end_date": "2026-03-10"},
    )
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "30"
    data = resp.get_json()
    assert data["success"] is False
    assert data["meta"]["error_code"] == "heavy_query_overloaded"


@patch("mes_dashboard.routes.production_history_routes.query_production_history")
def test_query_memory_guard_rejected(mock_query, client):
    mock_query.side_effect = MemoryError("rss limit exceeded")
    resp = client.post(
        "/api/production-history/query",
        json={"pj_types": ["GA"], "start_date": "2026-03-01", "end_date": "2026-03-10"},
    )
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "60"
    data = resp.get_json()
    assert data["success"] is False
    assert data["meta"]["error_code"] == "memory_guard_rejected"


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
@patch("mes_dashboard.routes.production_history_routes.compute_detail_page")
def test_page_memory_guard_rejected(mock_page, mock_spool, client):
    mock_spool.return_value = "/tmp/fake.parquet"
    mock_page.side_effect = MemoryError("rss limit")
    resp = client.post(
        "/api/production-history/page",
        json={"dataset_id": "ph-abc"},
    )
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["success"] is False
    assert data["meta"]["error_code"] == "memory_guard_rejected"


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
@patch("mes_dashboard.routes.production_history_routes.compute_matrix_view")
def test_matrix_memory_guard_rejected(mock_matrix, mock_spool, client):
    mock_spool.return_value = "/tmp/fake.parquet"
    mock_matrix.side_effect = MemoryError("rss limit")
    resp = client.post(
        "/api/production-history/matrix",
        json={"dataset_id": "ph-abc"},
    )
    assert resp.status_code == 503
    data = resp.get_json()
    assert data["success"] is False
    assert data["meta"]["error_code"] == "memory_guard_rejected"


# ── 4. Filter contract: /page and /matrix share the same filter schema ────────

@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
@patch("mes_dashboard.routes.production_history_routes.compute_detail_page")
def test_page_accepts_matrix_filter_fields(mock_page, mock_spool, client):
    mock_spool.return_value = "/tmp/fake.parquet"
    mock_page.return_value = {
        "rows": [], "pagination": {"page": 1, "per_page": 25, "total_rows": 0, "total_pages": 0}
    }
    resp = client.post(
        "/api/production-history/page",
        json={
            "dataset_id": "ph-abc",
            "workcenter_group": "焊接_DB",
            "spec": "SPEC-001",
            "equipment_id": "EQP-001",
        },
    )
    assert resp.status_code == 200
    # Verify the filter was passed through to compute_detail_page
    _, kwargs = mock_page.call_args
    call_args = mock_page.call_args[0]
    filter_arg = call_args[1] if len(call_args) > 1 else mock_page.call_args[1].get("filter_params", {})
    assert filter_arg.get("workcenter_group") == "焊接_DB"
    assert filter_arg.get("spec") == "SPEC-001"
    assert filter_arg.get("equipment_id") == "EQP-001"


@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
@patch("mes_dashboard.routes.production_history_routes.compute_matrix_view")
def test_matrix_accepts_same_filter_schema(mock_matrix, mock_spool, client):
    mock_spool.return_value = "/tmp/fake.parquet"
    mock_matrix.return_value = {"tree": [], "month_columns": []}
    resp = client.post(
        "/api/production-history/matrix",
        json={
            "dataset_id": "ph-abc",
            "workcenter_group": "焊接_DB",
            "spec": "SPEC-001",
            "equipment_id": "EQP-001",
        },
    )
    assert resp.status_code == 200
    call_args = mock_matrix.call_args[0]
    filter_arg = call_args[1] if len(call_args) > 1 else mock_matrix.call_args[1].get("filter_params", {})
    assert filter_arg.get("workcenter_group") == "焊接_DB"
    assert filter_arg.get("spec") == "SPEC-001"
    assert filter_arg.get("equipment_id") == "EQP-001"


# ── 5. Export query params match /page filter semantics ───────────────────────

@patch("mes_dashboard.routes.production_history_routes.get_spool_file_path")
@patch("mes_dashboard.routes.production_history_routes.stream_export")
def test_export_accepts_filter_query_params(mock_export, mock_spool, client):
    mock_spool.return_value = "/tmp/fake.parquet"
    mock_export.return_value = iter(["LotID,Type\n", "GA001,GA\n"])
    resp = client.get(
        "/api/production-history/export"
        "?dataset_id=ph-abc&workcenter_group=%E7%84%8A%E6%8E%A5_DB&spec=SPEC-001&equipment_id=EQP-001"
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    # Verify filter was passed to stream_export
    call_args = mock_export.call_args[0]
    filter_arg = call_args[1] if len(call_args) > 1 else {}
    assert filter_arg.get("workcenter_group") == "焊接_DB"
    assert filter_arg.get("spec") == "SPEC-001"
    assert filter_arg.get("equipment_id") == "EQP-001"


# ── 6. LOT trace: validation service unit tests ───────────────────────────────

class TestLotTraceGuards:
    def test_validate_lot_trace_same_cid_continues(self):
        """Same-cid parent mapping should be skipped without raising."""
        from mes_dashboard.services.production_history_service import (
            _resolve_lot_ids_with_trace,
        )
        from unittest.mock import patch as _patch

        def _fake_resolve(names):
            return {n: f"cid-{n}" for n in names}

        def _fake_split(cids):
            return {"child_to_parent": {cid: cid for cid in cids}, "cid_to_name": {}}

        with (
            _patch(
                "mes_dashboard.services.production_history_service._resolve_container_ids_by_names",
                side_effect=_fake_resolve,
            ),
            _patch(
                "mes_dashboard.services.lineage_engine.LineageEngine.resolve_split_ancestors",
                side_effect=_fake_split,
            ),
        ):
            result = _resolve_lot_ids_with_trace(["GA001"])
            assert "GA001" in result

    def test_validate_lot_trace_cross_lot_cycle_raises_valueerror(self):
        """A cross-lot cycle (A→B→A) should raise ValueError."""
        from mes_dashboard.services.production_history_service import (
            _resolve_lot_ids_with_trace,
        )
        from unittest.mock import patch as _patch

        def _fake_resolve(names):
            return {n: f"cid-{n}" for n in names}

        call_count = {"n": 0}

        def _fake_split(cids):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: GA001 → parent-B (new, not yet visited)
                return {
                    "child_to_parent": {"cid-GA001": "parent-B"},
                    "cid_to_name": {"parent-B": "LOT-B"},
                }
            else:
                # Second call: parent-B → cid-GA001 (already visited → cycle)
                return {
                    "child_to_parent": {"parent-B": "cid-GA001"},
                    "cid_to_name": {},
                }

        with (
            _patch(
                "mes_dashboard.services.production_history_service._resolve_container_ids_by_names",
                side_effect=_fake_resolve,
            ),
            _patch(
                "mes_dashboard.services.lineage_engine.LineageEngine.resolve_split_ancestors",
                side_effect=_fake_split,
            ),
        ):
            with pytest.raises(ValueError, match="循環"):
                _resolve_lot_ids_with_trace(["GA001"])

    def test_validate_query_params_missing_pj_types(self):
        from mes_dashboard.services.production_history_service import validate_query_params
        with pytest.raises(ValueError, match="pj_types"):
            validate_query_params({"start_date": "2026-03-01", "end_date": "2026-03-10"})

    def test_validate_query_params_max_date_range(self):
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
            MAX_DATE_RANGE_DAYS,
        )
        with pytest.raises(ValueError, match="日期區間超過上限"):
            validate_query_params({
                "pj_types": ["GA"],
                "start_date": "2020-01-01",
                "end_date": "2026-03-25",
            })

    def test_validate_query_params_bad_date_format(self):
        from mes_dashboard.services.production_history_service import validate_query_params
        with pytest.raises(ValueError, match="日期格式錯誤"):
            validate_query_params({
                "pj_types": ["GA"],
                "start_date": "01/03/2026",
                "end_date": "2026-03-10",
            })

    def test_end_date_exclusive_semantics(self):
        from mes_dashboard.services.production_history_service import validate_query_params
        result = validate_query_params({
            "pj_types": ["GA"],
            "start_date": "2026-03-01",
            "end_date": "2026-03-31",
        })
        assert result["end_date_exclusive"] == "2026-04-01"
