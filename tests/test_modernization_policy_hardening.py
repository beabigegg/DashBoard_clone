# -*- coding: utf-8 -*-
"""Hardening tests for modernization policy caching behavior."""

from __future__ import annotations

import json

from mes_dashboard.core import modernization_policy as policy


def test_scope_matrix_loader_returns_defensive_copy(tmp_path, monkeypatch):
    scope_file = tmp_path / "route_scope_matrix.json"
    scope_file.write_text(
        json.dumps({"in_scope": [{"route": "/wip-overview"}], "deferred": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(policy, "SCOPE_MATRIX_FILE", scope_file)
    policy.clear_modernization_policy_cache()

    payload = policy.load_scope_matrix()
    payload["in_scope"].append({"route": "/mutated"})

    fresh_payload = policy.load_scope_matrix()
    routes = [item["route"] for item in fresh_payload["in_scope"]]
    assert routes == ["/wip-overview"]


def test_scope_matrix_cache_refresh_requires_explicit_clear(tmp_path, monkeypatch):
    scope_file = tmp_path / "route_scope_matrix.json"
    scope_file.write_text(
        json.dumps({"in_scope": [{"route": "/before"}], "deferred": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(policy, "SCOPE_MATRIX_FILE", scope_file)
    policy.clear_modernization_policy_cache()
    assert [item["route"] for item in policy.load_scope_matrix()["in_scope"]] == ["/before"]

    scope_file.write_text(
        json.dumps({"in_scope": [{"route": "/after"}], "deferred": []}),
        encoding="utf-8",
    )
    assert [item["route"] for item in policy.load_scope_matrix()["in_scope"]] == ["/before"]

    policy.clear_modernization_policy_cache()
    assert [item["route"] for item in policy.load_scope_matrix()["in_scope"]] == ["/after"]


# ---------------------------------------------------------------------------
# AC-8: material-consumption registration assertions
# ---------------------------------------------------------------------------


class TestMaterialConsumptionRegistration:
    """AC-8: assert /material-consumption is registered in manifests and page_status."""

    def _load_asset_manifest(self) -> dict:
        import os
        manifest_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs",
            "migration",
            "full-modernization-architecture-blueprint",
            "asset_readiness_manifest.json",
        )
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_page_status(self) -> dict:
        import os
        page_status_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "page_status.json",
        )
        with open(page_status_path, encoding="utf-8") as f:
            return json.load(f)

    def test_asset_readiness_manifest_contains_material_consumption_key(self):
        """asset_readiness_manifest.json must have /material-consumption entry."""
        manifest = self._load_asset_manifest()
        assert "/material-consumption" in manifest.get("in_scope_required_assets", {}), (
            "asset_readiness_manifest.json missing '/material-consumption' key. "
            "This will crash gunicorn at startup."
        )

    def test_page_status_contains_material_consumption_in_drawer(self):
        """page_status.json must have /material-consumption page in drawer (查詢工具)."""
        page_status = self._load_page_status()
        pages = page_status.get("pages", [])
        mc_pages = [p for p in pages if p.get("route") == "/material-consumption"]
        assert len(mc_pages) >= 1, (
            "page_status.json missing '/material-consumption' page entry."
        )
        mc_page = mc_pages[0]
        assert mc_page.get("drawer_id") == "drawer", (
            f"Expected drawer for /material-consumption, got {mc_page.get('drawer_id')!r}"
        )


# ---------------------------------------------------------------------------
# AC-7: downtime-analysis registration assertions
# ---------------------------------------------------------------------------


class TestDowntimeAnalysisPage:
    """AC-7: assert /downtime-analysis is registered in manifests and page_status."""

    def _load_asset_manifest(self) -> dict:
        import os
        manifest_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs",
            "migration",
            "full-modernization-architecture-blueprint",
            "asset_readiness_manifest.json",
        )
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_page_status(self) -> dict:
        import os
        page_status_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "page_status.json",
        )
        with open(page_status_path, encoding="utf-8") as f:
            return json.load(f)

    def _load_scope_matrix(self) -> dict:
        import os
        matrix_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "docs",
            "migration",
            "full-modernization-architecture-blueprint",
            "route_scope_matrix.json",
        )
        with open(matrix_path, encoding="utf-8") as f:
            return json.load(f)

    def test_page_status_contains_downtime_analysis_in_drawer_2(self):
        """page_status.json must have /downtime-analysis in drawer-2 (歷史報表)."""
        page_status = self._load_page_status()
        pages = page_status.get("pages", [])
        da_pages = [p for p in pages if p.get("route") == "/downtime-analysis"]
        assert len(da_pages) >= 1, (
            "page_status.json missing '/downtime-analysis' page entry. "
            "This will leave an orphan sidebar entry."
        )
        da_page = da_pages[0]
        assert da_page.get("drawer_id") == "drawer-2", (
            f"Expected drawer_id='drawer-2' for /downtime-analysis, "
            f"got {da_page.get('drawer_id')!r}"
        )

    def test_asset_readiness_manifest_contains_downtime_analysis(self):
        """asset_readiness_manifest.json must have /downtime-analysis entry.

        Omitting it crashes gunicorn at startup via _validate_in_scope_asset_readiness().
        """
        manifest = self._load_asset_manifest()
        assert "/downtime-analysis" in manifest.get("in_scope_required_assets", {}), (
            "asset_readiness_manifest.json missing '/downtime-analysis' key. "
            "This will crash gunicorn at startup."
        )
        asset_list = manifest["in_scope_required_assets"]["/downtime-analysis"]
        assert len(asset_list) >= 1, (
            "asset_readiness_manifest.json entry for /downtime-analysis has no asset paths."
        )

    def test_route_scope_matrix_contains_downtime_analysis(self):
        """route_scope_matrix.json must classify /downtime-analysis as in-scope."""
        matrix = self._load_scope_matrix()
        in_scope_routes = [item.get("route") for item in matrix.get("in_scope", [])]
        assert "/downtime-analysis" in in_scope_routes, (
            "route_scope_matrix.json missing '/downtime-analysis' in 'in_scope' list."
        )
