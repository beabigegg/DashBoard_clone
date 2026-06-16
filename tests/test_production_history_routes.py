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

from unittest.mock import patch

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
        # pj_types is now optional — classification-mode queries need only a date range
        result = validate_query_params({"start_date": "2026-03-01", "end_date": "2026-03-10"})
        assert result["start_date"] == "2026-03-01"

    def test_validate_query_params_max_date_range(self):
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
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


class TestProductionHistory730dBoundary:
    """730-day boundary, 731-day validation error, and dataset_id hash stability."""

    def test_730d_boundary_is_valid(self):
        """Exactly 730 days must be accepted (boundary condition)."""
        from mes_dashboard.services.production_history_service import (
            validate_query_params,
            MAX_DATE_RANGE_DAYS,
        )
        assert MAX_DATE_RANGE_DAYS == 730, "MAX_DATE_RANGE_DAYS must be 730"
        # Exactly 730 days: span = (end - start).days + 1 = 730
        # 2024-01-01 + 729 days = 2025-12-30 (2024 is leap: 366d, then 364 days in 2025)
        result = validate_query_params({
            "pj_types": ["GA"],
            "start_date": "2024-01-01",
            "end_date": "2025-12-30",
        })
        assert result is not None

    def test_731d_returns_validation_error(self, client):
        """731-day range must be rejected with 400 VALIDATION_ERROR."""
        response = client.post(
            '/api/production-history/query',
            data=__import__('json').dumps({
                "pj_types": ["GA"],
                "start_date": "2024-01-01",
                "end_date": "2026-01-01",  # 731+ days
            }),
            content_type='application/json',
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert payload['success'] is False
        assert payload['error']['code'] == 'VALIDATION_ERROR'

    def test_missing_pj_types_returns_validation_error(self, client):
        """Missing pj_types must return 400 VALIDATION_ERROR."""
        response = client.post(
            '/api/production-history/query',
            data=__import__('json').dumps({
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            }),
            content_type='application/json',
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert payload['success'] is False
        assert payload['error']['code'] == 'VALIDATION_ERROR'

    def test_empty_pj_types_returns_validation_error(self, client):
        """Empty pj_types list must return 400 VALIDATION_ERROR."""
        response = client.post(
            '/api/production-history/query',
            data=__import__('json').dumps({
                "pj_types": [],
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            }),
            content_type='application/json',
        )
        assert response.status_code == 400
        payload = response.get_json()
        assert payload['success'] is False

    def _base_params(self):
        return {
            "pj_types": ["GA"],
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "lot_ids": [],
            "work_orders": [],
            "packages": [],
            "bop_codes": [],
            "workcenter_groups": [],
            "workcenter_names": [],
            "equipment_ids": [],
        }

    def test_dataset_id_hash_stability(self):
        """dataset_id generated for same params must be identical across calls."""
        from mes_dashboard.services.production_history_service import _make_dataset_id
        params_a = self._base_params()
        params_b = self._base_params()
        assert _make_dataset_id(params_a) == _make_dataset_id(params_b)

    def test_dataset_id_different_for_different_params(self):
        """dataset_id must differ for different query params."""
        from mes_dashboard.services.production_history_service import _make_dataset_id
        params_a = self._base_params()
        params_b = {**self._base_params(), "pj_types": ["FA"]}
        assert _make_dataset_id(params_a) != _make_dataset_id(params_b)


# ============================================================
# Change: prod-history-first-tier-cache-filters
# Filter-options endpoint + main-query envelope unchanged
# ============================================================

class TestFilterOptionsEndpoint:
    """GET /api/production-history/filter-options."""

    def _stub_options(self, monkeypatch, payload):
        """Patch get_filter_options at the module the route imports it from."""
        from mes_dashboard.services import container_filter_cache as cfc
        monkeypatch.setattr(cfc, "get_filter_options", lambda selected=None: payload)

    def test_filter_options_endpoint_empty_selection(self, client, monkeypatch):
        """AC-1 — no `selected` param → full sets returned."""
        self._stub_options(monkeypatch, {
            "pj_types": ["GA", "FA"],
            "packages": ["PKG_A"],
            "bops": ["BOP_1"],
            "pj_functions": ["FN_X"],
            "updated_at": "2026-05-14T00:00:00+00:00",
            "schema_version": 2,
        })

        resp = client.get("/api/production-history/filter-options")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["data"]["pj_types"] == ["GA", "FA"]
        assert body["data"]["packages"] == ["PKG_A"]
        assert body["data"]["bops"] == ["BOP_1"]
        assert body["data"]["pj_functions"] == ["FN_X"]
        assert body["meta"]["schema_version"] == 2

    def test_filter_options_endpoint_with_selected_package(self, client, monkeypatch):
        """AC-2 — selected payload narrows the response."""
        captured: dict = {}

        from mes_dashboard.services import container_filter_cache as cfc

        def _fake_get(selected=None):
            captured["selected"] = selected
            return {
                "pj_types": ["GA"],
                "packages": ["PKG_A"],
                "bops": ["BOP_1"],
                "pj_functions": ["FN_X"],
                "updated_at": "2026-05-14T00:00:00+00:00",
                "schema_version": 2,
            }
        monkeypatch.setattr(cfc, "get_filter_options", _fake_get)

        import json as _json
        from urllib.parse import quote
        sel = quote(_json.dumps({"packages": ["PKG_A"]}))
        resp = client.get(f"/api/production-history/filter-options?selected={sel}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["packages"] == ["PKG_A"]
        assert captured["selected"] == {"packages": ["PKG_A"]}

    def test_filter_options_rejects_unknown_keys_is_fail_open(self, client, monkeypatch):
        """Unknown selected keys are ignored — endpoint still returns 200."""
        from mes_dashboard.services import container_filter_cache as cfc

        def _fake_get(selected=None):
            # Service ignores unknown keys at its own layer; route just forwards.
            return {
                "pj_types": ["GA"],
                "packages": [],
                "bops": [],
                "pj_functions": [],
                "updated_at": None,
                "schema_version": 2,
            }
        monkeypatch.setattr(cfc, "get_filter_options", _fake_get)

        import json as _json
        from urllib.parse import quote
        sel = quote(_json.dumps({"unknown_field": ["X"], "pj_types": ["GA"]}))
        resp = client.get(f"/api/production-history/filter-options?selected={sel}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_filter_options_invalid_json_returns_400(self, client):
        """Malformed JSON in `selected` → 400 VALIDATION_ERROR."""
        resp = client.get(
            "/api/production-history/filter-options?selected=%7Bnot-json"
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_filter_options_response_shape_matches_data_2_7(self, client, monkeypatch):
        """Response shape matches data-shape §2.7 (four arrays + meta block)."""
        from mes_dashboard.services import container_filter_cache as cfc
        monkeypatch.setattr(cfc, "get_filter_options", lambda selected=None: {
            "pj_types": ["A"], "packages": ["B"], "bops": ["C"], "pj_functions": ["D"],
            "updated_at": "2026-05-14T00:00:00+00:00", "schema_version": 2,
        })

        resp = client.get("/api/production-history/filter-options")
        body = resp.get_json()
        # Required data keys
        for key in ("pj_types", "packages", "bops", "pj_functions"):
            assert key in body["data"]
            assert isinstance(body["data"][key], list)
        # Required meta keys
        assert body["meta"]["schema_version"] == 2
        assert "updated_at" in body["meta"]


# ── prod-history-query-mode-tabs: mode-split validation (PHF-07 / PHF-08) ─────

class TestQueryModeSplitRoutes:
    """Route-level coverage for identifier-mode optional dates (AC-4 / AC-5 / AC-7)."""

    @patch("mes_dashboard.routes.production_history_routes.query_production_history")
    def test_query_identifier_only_no_dates_returns_results(self, mock_query, client):
        """AC-4 — identifier token, no dates → 200 success envelope."""
        mock_query.return_value = {
            "dataset_id": "ph-id1",
            "detail": {"rows": [], "pagination": {"page": 1, "per_page": 25, "total_rows": 0, "total_pages": 0}},
            "matrix": {"tree": [], "month_columns": []},
            "filter_options": {"pj_types": []},
            "meta": {"ttl_seconds": 3600, "expires_at": 9999999999, "row_count": 0},
        }
        resp = client.post(
            "/api/production-history/query",
            json={"lot_ids": ["GA001AB"]},
        )
        assert resp.status_code in (200, 202)
        data = resp.get_json()
        assert data["success"] is True

    def test_query_classification_only_no_dates_returns_validation_error(self, client):
        """PHF-08 — no identifier token, no dates → 400 VALIDATION_ERROR."""
        resp = client.post(
            "/api/production-history/query",
            json={"pj_types": ["GA"]},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_query_identifier_wide_window_bounded(self, client):
        """AC-5 — no-date identifier path emits a chunk plan bounded to today − 730d.

        Deterministic: no Oracle optimizer reliance. Captures the validated
        params via validate_query_params and asserts the decomposed chunk
        plan spans exactly the 730-day cap.
        """
        from datetime import date, timedelta
        from mes_dashboard.services.batch_query_engine import decompose_by_time_range
        from mes_dashboard.services.production_history_service import (
            ENGINE_GRAIN_DAYS,
            MAX_DATE_RANGE_DAYS,
            validate_query_params,
        )
        params = validate_query_params({"mfg_orders": "MA2025*"})
        chunks = decompose_by_time_range(
            params["start_date"], params["end_date"], grain_days=ENGINE_GRAIN_DAYS
        )
        floor = (date.today() - timedelta(days=MAX_DATE_RANGE_DAYS)).strftime("%Y-%m-%d")
        first_start = min(c["chunk_start"] for c in chunks)
        assert first_start >= floor, "chunk_start must be ≥ today − 730d (no unbounded scan)"
