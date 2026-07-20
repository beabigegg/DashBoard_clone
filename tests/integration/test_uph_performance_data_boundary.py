# -*- coding: utf-8 -*-
"""Data boundary tests for UPH Performance (add-uph-performance-page).

All tests use synthetic parquet fixtures or route-level mocks -- no live
Oracle/Redis. Covers UPH-03's runtime-empty behavior and AC-8: a
BondUPH/fHCM_UPH zero-row result is a graceful state-empty (never an error),
and no internal Oracle PARAMETER_NAME string ever leaks into a JSON response.

pytestmark = pytest.mark.integration
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytestmark = pytest.mark.integration

_SPOOL_SCHEMA = pa.schema([
    pa.field("LOT_ID", pa.string(), nullable=False),
    pa.field("EQUIPMENT_ID", pa.string(), nullable=False),
    pa.field("EQUIPMENT_FAMILY", pa.string(), nullable=False),
    pa.field("EVENT_TIME", pa.timestamp("us"), nullable=False),
    pa.field("PARAMETER_NAME", pa.string(), nullable=False),
    pa.field("UPH_VALUE", pa.float64(), nullable=True),
    pa.field("WORKCENTERNAME", pa.string(), nullable=True),
    pa.field("MODEL", pa.string(), nullable=True),
    pa.field("DB_WB_LABEL", pa.string(), nullable=True),
    pa.field("PACKAGE", pa.string(), nullable=True),
    pa.field("PJ_TYPE", pa.string(), nullable=True),
    pa.field("PJ_BOP", pa.string(), nullable=True),
    pa.field("PJ_FUNCTION", pa.string(), nullable=True),
    pa.field("DIE_COUNT", pa.string(), nullable=True),
    pa.field("WIRE_COUNT", pa.string(), nullable=True),
    pa.field("coarse_filter_hash", pa.string(), nullable=False),
])


def _write_empty_spool(tmp_path) -> str:
    path = str(tmp_path / "empty_spool.parquet")
    table = pa.table(
        {f.name: pa.array([], type=f.type) for f in _SPOOL_SCHEMA},
        schema=_SPOOL_SCHEMA,
    )
    pq.write_table(table, path)
    return path


def _make_app():
    from mes_dashboard.app import create_app
    return create_app("testing")


class TestZeroRowEmptyState:
    """UPH-03/AC-8: zero rows for either family returns empty, not an error."""

    def test_zero_rows_for_bonduph_returns_empty_not_error(self, tmp_path, monkeypatch):
        spool_path = _write_empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/trend?query_id=qid")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["labels"] == []
        assert data["data"]["series"] == []

    def test_zero_rows_for_fhcm_uph_returns_empty_not_error(self, tmp_path, monkeypatch):
        spool_path = _write_empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.get("/api/uph-performance/detail?query_id=qid")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["rows"] == []
        assert data["data"]["meta"]["total_count"] == 0


class TestNoParameterNameLeak:
    """AC-8: internal Oracle PARAMETER_NAME values must never leak into a response."""

    def test_empty_state_message_is_generic_no_parameter_name_leak(self, tmp_path, monkeypatch):
        spool_path = _write_empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )

        app = _make_app()
        with app.test_client() as client:
            for url in (
                "/api/uph-performance/filter-options?query_id=qid",
                "/api/uph-performance/trend?query_id=qid",
                "/api/uph-performance/ranking?query_id=qid",
                "/api/uph-performance/detail?query_id=qid",
            ):
                resp = client.get(url)
                body_text = resp.get_data(as_text=True)
                assert "BondUPH" not in body_text, f"{url} leaked BondUPH: {body_text}"
                assert "fHCM_UPH" not in body_text, f"{url} leaked fHCM_UPH: {body_text}"


class TestMalformedDateRangeAtRoute:
    """Malformed date-range boundary cases exercised through the real HTTP
    route (POST /api/uph-performance/spool), not just the service-level unit
    test in tests/test_uph_performance_sql_builder.py. Confirms
    parse_json_payload -> validate_uph_performance_params -> 400 round-trips
    correctly end-to-end, and that the 730-day cap boundary itself (not
    strictly-over) succeeds per the "over-limit boundary tests must strictly
    exceed the cap" test-discipline rule."""

    def _post_spool(self, client, payload):
        return client.post(
            "/api/uph-performance/spool",
            json=payload,
            content_type="application/json",
        )

    def test_malformed_date_format_returns_400_at_route(self):
        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "not-a-date",
                "date_to": "2026-01-02",
            })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.get_json()}"
        assert resp.get_json()["success"] is False

    def test_date_to_before_date_from_returns_400_at_route(self):
        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "2026-02-01",
                "date_to": "2026-01-01",
            })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.get_json()}"
        assert resp.get_json()["success"] is False

    def test_date_range_731_days_strictly_over_cap_returns_400(self):
        """SYS-04/UPH-01: 731 days (strictly > 730) must be rejected."""
        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "2026-01-01",
                "date_to": "2028-01-02",  # 731 days later (2026 is not a leap year cross)
            })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.get_json()}"

    def test_date_range_exactly_730_days_succeeds_at_boundary(self, monkeypatch):
        """The 730-day cap itself (not strictly-over) must succeed -- the
        boundary is a valid range, not a rejection point."""
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda *a, **kw: ("job-boundary-730", None, None),
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "2026-01-01",
                "date_to": "2027-12-31",  # exactly 730 days
            })
        assert resp.status_code == 202, f"Expected 202 at exact 730-day boundary, got {resp.status_code}: {resp.get_json()}"

    def test_wrong_type_date_field_returns_400_not_500(self):
        """date_from as a non-string JSON type (integer) must degrade to a
        graceful 400, never an unhandled 500 (wrong-type data boundary)."""
        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": 20260101,
                "date_to": "2026-01-02",
            })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.get_json()}"
        assert resp.get_json()["success"] is False


class TestFamilyEnumBoundaryAtRoute:
    """UPH-02 family enum boundary/wrong-type cases through the real route."""

    def _post_spool(self, client, payload, monkeypatch=None):
        return client.post(
            "/api/uph-performance/spool",
            json=payload,
            content_type="application/json",
        )

    def test_family_lowercase_accepted_case_insensitively(self, monkeypatch):
        """families value is upper()-compared for validation; a lowercase
        'gdba' must not be spuriously rejected as outside {GDBA, GWBA}."""
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda *a, **kw: ("job-lowercase-family", None, None),
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "2026-01-01",
                "date_to": "2026-01-02",
                "families": ["gdba"],
            })
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.get_json()}"

    def test_family_wrong_type_scalar_string_normalized_not_rejected(self, monkeypatch):
        """families sent as a bare scalar string (not a JSON array) -- a
        wrong-type-data boundary case -- must be normalized to a one-element
        list rather than crashing or silently being ignored."""
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda *a, **kw: ("job-scalar-family", None, None),
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "2026-01-01",
                "date_to": "2026-01-02",
                "families": "GDBA",  # scalar, not ["GDBA"]
            })
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.get_json()}"

    def test_equipment_ids_at_max_200_succeeds_at_boundary(self, monkeypatch):
        """api-contract.md equipment_ids max=200: exactly 200 IDs is the valid
        boundary and must succeed (not the rejection point)."""
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: True,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.enqueue_query_job",
            lambda *a, **kw: ("job-eq-200", None, None),
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )
        monkeypatch.setattr(
            "mes_dashboard.core.permissions.get_owner_token", lambda: "test-user",
        )

        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "2026-01-01",
                "date_to": "2026-01-02",
                "equipment_ids": [f"GDBA-{i:04d}" for i in range(200)],
            })
        assert resp.status_code == 202, f"Expected 202 at exact 200-item boundary, got {resp.status_code}: {resp.get_json()}"

    def test_equipment_ids_over_200_strictly_exceeds_cap_returns_400(self):
        """201 IDs (strictly > 200) must be rejected -- pairs with the
        exact-200-succeeds boundary test above."""
        app = _make_app()
        with app.test_client() as client:
            resp = self._post_spool(client, {
                "date_from": "2026-01-01",
                "date_to": "2026-01-02",
                "equipment_ids": [f"GDBA-{i:04d}" for i in range(201)],
            })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.get_json()}"


class TestFineFilterAxisNarrowing:
    """One-of-N filter axes: test each axis EMPTY while a sibling is
    populated (CLAUDE.md test-discipline promoted learning), exercised
    against the REAL DuckDB get_filter_options()/get_detail() mechanism
    (not a route-level mock) -- confirms _build_filter_where's AND-combine
    actually narrows results per-axis, and doesn't conflate "any filter
    present" with a specific column."""

    def _write_narrowing_spool(self, tmp_path) -> str:
        path = str(tmp_path / "narrowing_spool.parquet")
        table = pa.table({
            "LOT_ID": ["L1", "L2", "L3"],
            "EQUIPMENT_ID": ["GDBA-01", "GDBA-02", "GWBA-01"],
            "EQUIPMENT_FAMILY": ["GDBA", "GDBA", "GWBA"],
            "EVENT_TIME": pd.to_datetime([
                "2026-01-01 01:00:00", "2026-01-01 02:00:00", "2026-01-01 03:00:00",
            ]),
            "PARAMETER_NAME": ["BondUPH", "BondUPH", "fHCM_UPH"],
            "UPH_VALUE": [100.0, 80.0, 60.0],
            "WORKCENTERNAME": ["焊接_DB_1線", "焊接_DB_2線", "焊接_WB_1線"],
            "MODEL": ["MODEL-A", "MODEL-B", "MODEL-C"],
            "DB_WB_LABEL": ["焊接_DB", "焊接_DB", "焊接_WB"],
            "PACKAGE": ["PKG-A", "PKG-B", "PKG-A"],
            "PJ_TYPE": ["TYPE-1", "TYPE-2", "TYPE-1"],
            "DIE_COUNT": ["12", "24", "12"],
            "WIRE_COUNT": ["4", "8", "4"],
        })
        pq.write_table(table, path)
        return path

    def test_workcenter_populated_pj_type_empty_narrows_equipment_options(self, tmp_path):
        """workcenter_name axis populated, pj_type axis EMPTY -- must narrow
        equipment_id_options to only the matching workcenter's equipment,
        independent of pj_type."""
        import duckdb
        from mes_dashboard.services.uph_performance_service import get_filter_options

        spool_path = self._write_narrowing_spool(tmp_path)
        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_filter_options(
                spool_path,
                {"workcenter_name": ["焊接_DB_1線"], "pj_type": []},
            )

        assert result["equipment_id_options"] == ["GDBA-01"], (
            f"Expected only GDBA-01 (matching workcenter), got: {result['equipment_id_options']}"
        )

    def test_pj_type_populated_workcenter_empty_narrows_equipment_options(self, tmp_path):
        """The sibling axis: pj_type populated, workcenter_name EMPTY --
        must narrow independently via its own column, not the workcenter one."""
        import duckdb
        from mes_dashboard.services.uph_performance_service import get_filter_options

        spool_path = self._write_narrowing_spool(tmp_path)
        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_filter_options(
                spool_path,
                {"pj_type": ["TYPE-1"], "workcenter_name": []},
            )

        assert sorted(result["equipment_id_options"]) == ["GDBA-01", "GWBA-01"], (
            f"Expected GDBA-01+GWBA-01 (matching TYPE-1 across both families), "
            f"got: {result['equipment_id_options']}"
        )

    def test_both_axes_empty_returns_unnarrowed_full_option_set(self, tmp_path):
        """Control case: neither axis populated -- all distinct equipment IDs
        returned, confirming the empty/empty case isn't itself over-filtered."""
        import duckdb
        from mes_dashboard.services.uph_performance_service import get_filter_options

        spool_path = self._write_narrowing_spool(tmp_path)
        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_filter_options(spool_path, {"pj_type": [], "workcenter_name": []})

        assert sorted(result["equipment_id_options"]) == ["GDBA-01", "GDBA-02", "GWBA-01"]

    def test_detail_per_page_over_cap_actually_truncates_real_rows(self, tmp_path):
        """Real-data companion to the mocked test_detail_per_page_capped_at_200
        in test_uph_performance_rq_async.py: get_detail() itself must truncate
        to 200 rows when per_page=500 is requested against a >200-row spool
        (over-limit boundary, strictly exceeding the cap, not equal to it)."""
        import duckdb
        from mes_dashboard.services.uph_performance_service import get_detail

        path = str(tmp_path / "big_spool.parquet")
        n = 250
        table = pa.table({
            "LOT_ID": [f"L{i}" for i in range(n)],
            "EQUIPMENT_ID": [f"GDBA-{i:04d}" for i in range(n)],
            "EVENT_TIME": pd.to_datetime(["2026-01-01 01:00:00"] * n),
            "UPH_VALUE": [100.0] * n,
            "PACKAGE": ["PKG-A"] * n,
            "PJ_TYPE": ["TYPE-1"] * n,
            "WORKCENTERNAME": ["焊接_DB_1線"] * n,
            "MODEL": ["MODEL-A"] * n,
        })
        pq.write_table(table, path)

        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_detail(path, filters=None, page=1, per_page=500)

        assert len(result["rows"]) == 200, (
            f"per_page=500 against a 250-row spool must truncate to the "
            f"200-row cap, got {len(result['rows'])} rows"
        )
        assert result["meta"]["per_page"] == 200


class TestFilterOptionsCrossFilterNarrowing:
    """Cross-filter narrowing across fine-filter axes, with a mandatory
    self-exclusion guarantee: selecting a value on axis A narrows every
    OTHER axis's option list, but must NEVER narrow axis A's own option
    list down to just what's already selected on A (that would silently
    break A's own MultiSelect's ability to add more values)."""

    def _write_cross_filter_spool(self, tmp_path) -> str:
        """4 rows spanning 2 distinct values each on pj_type/package/die_count/
        wire_count, with L1 the only row matching BOTH pj_type=TYPE-A and
        package=PKG-1 -- lets a single fixture prove single-axis narrowing,
        self-exclusion, and 2-axis AND-narrowing all at once."""
        path = str(tmp_path / "cross_filter_spool.parquet")
        table = pa.table({
            "LOT_ID": ["L1", "L2", "L3", "L4"],
            "EQUIPMENT_ID": ["GDBA-01", "GDBA-02", "GDBA-03", "GDBA-04"],
            "EQUIPMENT_FAMILY": ["GDBA", "GDBA", "GDBA", "GDBA"],
            "EVENT_TIME": pd.to_datetime([
                "2026-01-01 01:00:00", "2026-01-01 02:00:00",
                "2026-01-01 03:00:00", "2026-01-01 04:00:00",
            ]),
            "PARAMETER_NAME": ["BondUPH", "BondUPH", "BondUPH", "BondUPH"],
            "UPH_VALUE": [100.0, 90.0, 80.0, 70.0],
            "WORKCENTERNAME": ["WC1", "WC2", "WC3", "WC4"],
            "PACKAGE": ["PKG-1", "PKG-2", "PKG-1", "PKG-3"],
            "PJ_TYPE": ["TYPE-A", "TYPE-A", "TYPE-B", "TYPE-B"],
            "DIE_COUNT": ["12", "24", "12", "36"],
            "WIRE_COUNT": ["4", "8", "4", "16"],
        })
        pq.write_table(table, path)
        return path

    def test_selecting_pj_type_narrows_other_axes_options(self, tmp_path):
        """filters={"pj_type": ["TYPE-A"]} -- package/die_count/wire_count
        option lists must only contain values co-occurring with TYPE-A rows
        (L1/L2), not the full unfiltered spool-wide set."""
        import duckdb
        from mes_dashboard.services.uph_performance_service import get_filter_options

        spool_path = self._write_cross_filter_spool(tmp_path)
        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_filter_options(spool_path, {"pj_type": ["TYPE-A"]})

        assert sorted(result["package_options"]) == ["PKG-1", "PKG-2"], (
            f"package_options must narrow to TYPE-A's co-occurring packages, "
            f"got: {result['package_options']}"
        )
        assert sorted(result["die_count_options"]) == ["12", "24"], (
            f"die_count_options must narrow to TYPE-A's co-occurring die counts, "
            f"got: {result['die_count_options']}"
        )
        assert sorted(result["wire_count_options"]) == ["4", "8"], (
            f"wire_count_options must narrow to TYPE-A's co-occurring wire counts, "
            f"got: {result['wire_count_options']}"
        )

    def test_get_filter_options_never_self_narrows(self, tmp_path):
        """THE critical property this task exists for: filters={"pj_type":
        ["TYPE-A"]} must NOT collapse pj_type_options down to just
        ["TYPE-A"] -- the fixture has 2 distinct PJ_TYPE values (TYPE-A,
        TYPE-B) and both must still be reachable so the pj_type MultiSelect
        can still add TYPE-B."""
        import duckdb
        from mes_dashboard.services.uph_performance_service import get_filter_options

        spool_path = self._write_cross_filter_spool(tmp_path)
        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_filter_options(spool_path, {"pj_type": ["TYPE-A"]})

        assert sorted(result["pj_type_options"]) == ["TYPE-A", "TYPE-B"], (
            f"pj_type_options must never be narrowed by pj_type's own "
            f"selection -- got: {result['pj_type_options']}"
        )

    def test_two_simultaneous_axes_and_narrow_third_but_not_each_other(self, tmp_path):
        """filters={"pj_type": ["TYPE-A"], "package": ["PKG-1"]}:
        - die_count_options (a third, unselected axis) is narrowed by BOTH
          selections combined (AND semantics, only L1 matches both) -> ["12"].
        - pj_type_options is narrowed only by package's selection (TYPE-A and
          TYPE-B both have a PKG-1 row: L1, L3) -> NOT narrowed by its own
          TYPE-A selection.
        - package_options is narrowed only by pj_type's selection (TYPE-A
          rows: L1=PKG-1, L2=PKG-2) -> NOT narrowed by its own PKG-1
          selection.
        """
        import duckdb
        from mes_dashboard.services.uph_performance_service import get_filter_options

        spool_path = self._write_cross_filter_spool(tmp_path)
        with patch(
            "mes_dashboard.services.uph_performance_service._get_duckdb_conn",
            return_value=duckdb.connect(),
        ):
            result = get_filter_options(
                spool_path, {"pj_type": ["TYPE-A"], "package": ["PKG-1"]},
            )

        assert result["die_count_options"] == ["12"], (
            f"die_count_options must be AND-narrowed by both pj_type=TYPE-A "
            f"and package=PKG-1 (only L1 matches both), got: "
            f"{result['die_count_options']}"
        )
        assert sorted(result["pj_type_options"]) == ["TYPE-A", "TYPE-B"], (
            f"pj_type_options must be narrowed only by package=PKG-1 (not "
            f"its own pj_type selection) -- both TYPE-A (L1) and TYPE-B (L3) "
            f"have a PKG-1 row, got: {result['pj_type_options']}"
        )
        assert sorted(result["package_options"]) == ["PKG-1", "PKG-2"], (
            f"package_options must be narrowed only by pj_type=TYPE-A (not "
            f"its own package selection) -- TYPE-A rows are PKG-1 (L1) and "
            f"PKG-2 (L2), got: {result['package_options']}"
        )


class TestStateDistinctness:
    """State-empty must be distinguishable from job-failed / worker-unavailable / expired."""

    def test_empty_state_distinct_from_job_failed_state(self, tmp_path, monkeypatch):
        spool_path = _write_empty_spool(tmp_path)
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: spool_path,
        )
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.get_job_status",
            lambda prefix, job_id: {"job_id": job_id, "status": "failed", "error": "boom"},
        )

        app = _make_app()
        with app.test_client() as client:
            empty_resp = client.get("/api/uph-performance/detail?query_id=qid")
            failed_resp = client.get("/api/uph-performance/spool/status?job_id=jid")

        assert empty_resp.status_code == 200
        assert empty_resp.get_json()["success"] is True
        assert failed_resp.status_code == 200  # status poll itself succeeds
        assert failed_resp.get_json()["data"]["status"] == "failed"

    def test_empty_state_distinct_from_worker_unavailable_state(self, monkeypatch):
        monkeypatch.setattr(
            "mes_dashboard.services.async_query_job_service.is_async_available",
            lambda: False,
        )
        monkeypatch.setattr(
            "mes_dashboard.routes.uph_performance_routes._get_spool_path",
            lambda key: None,
        )

        app = _make_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/uph-performance/spool",
                json={"date_from": "2026-01-01", "date_to": "2026-01-02"},
                content_type="application/json",
            )
        assert resp.status_code == 503
        assert resp.get_json()["success"] is False

    def test_state_expired_410_distinct_from_state_empty(self, tmp_path, monkeypatch):
        spool_path = _write_empty_spool(tmp_path)

        app = _make_app()

        # Expired/missing spool -> 410
        with app.test_client() as client:
            with patch(
                "mes_dashboard.routes.uph_performance_routes._get_spool_path",
                return_value=None,
            ):
                expired_resp = client.get("/api/uph-performance/detail?query_id=expired-qid")

        assert expired_resp.status_code == 410

        # Valid spool with zero rows -> 200, empty
        with app.test_client() as client:
            with __import__("unittest.mock", fromlist=["patch"]).patch(
                "mes_dashboard.routes.uph_performance_routes._get_spool_path",
                return_value=spool_path,
            ):
                empty_resp = client.get("/api/uph-performance/detail?query_id=empty-qid")

        assert empty_resp.status_code == 200
        assert empty_resp.get_json()["data"]["rows"] == []
