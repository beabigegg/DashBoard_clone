# -*- coding: utf-8 -*-
"""Contract tests for the 10 new /api/production-achievement/* endpoints
(production-achievement-overhaul) and the redefined
ProductionAchievementReportResponse 5-inline-array envelope.

Mirrors tests/contract/test_uph_performance_contract.py's structure.
Response-shape assertions per api-contract.md rows 273-282 and
data-shape-contract.md §3.28.4/§3.30-§3.34.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).parent.parent.parent
_API_CONTRACT_PATH = _REPO_ROOT / "contracts" / "api" / "api-contract.md"
_OPENAPI_PATH = _REPO_ROOT / "contracts" / "openapi.json"
_API_OPENAPI_PATH = _REPO_ROOT / "contracts" / "api" / "openapi.json"


class TestTenNewEndpointRowsPresent:
    """AC-6: all 10 new endpoint rows are present in api-contract.md."""

    def test_all_ten_new_endpoint_rows_present_in_api_contract(self):
        content = _API_CONTRACT_PATH.read_text(encoding="utf-8")
        # NOTE: production-achievement-oracle-plan-source removed the 2
        # daily-plans rows this list originally had (10 -> 8) -- targets are
        # now Oracle-sourced (business-rules.md PA-11), see api-contract.md
        # Compatibility Notes.
        expected_rows = [
            ("GET", "/api/production-achievement/package-lf-map"),
            ("PUT", "/api/production-achievement/package-lf-map"),
            ("DELETE", "/api/production-achievement/package-lf-map/{raw}"),
            ("GET", "/api/production-achievement/workcenter-merge-map"),
            ("PUT", "/api/production-achievement/workcenter-merge-map"),
            ("DELETE", "/api/production-achievement/workcenter-merge-map/{raw}"),
            ("GET", "/api/production-achievement/known-package-lf-values"),
            ("GET", "/api/production-achievement/known-workcenter-groups"),
        ]
        missing = []
        for method, path in expected_rows:
            pattern = rf"\|\s*{method}\s*\|\s*{re.escape(path)}\s*\|"
            if not re.search(pattern, content):
                missing.append(f"{method} {path}")
        assert not missing, f"Missing endpoint row(s) in api-contract.md: {missing}"

    def test_ten_endpoints_resolve_in_both_openapi_export_paths(self):
        """AC-6/AC-13: cdd-kit openapi export must be re-run for BOTH output
        paths whenever the schema-version bumps (ci-gates.md Workflow safety
        net) -- verify both contracts/openapi.json and
        contracts/api/openapi.json agree on all 10 new operations."""
        expected_ops = [
            ("get", "/api/production-achievement/package-lf-map"),
            ("put", "/api/production-achievement/package-lf-map"),
            ("delete", "/api/production-achievement/package-lf-map/{raw}"),
            ("get", "/api/production-achievement/workcenter-merge-map"),
            ("put", "/api/production-achievement/workcenter-merge-map"),
            ("delete", "/api/production-achievement/workcenter-merge-map/{raw}"),
            ("get", "/api/production-achievement/known-package-lf-values"),
            ("get", "/api/production-achievement/known-workcenter-groups"),
        ]
        for openapi_path in (_OPENAPI_PATH, _API_OPENAPI_PATH):
            if not openapi_path.exists():
                pytest.skip(f"{openapi_path} not found -- run cdd-kit openapi export first")
            doc = json.loads(openapi_path.read_text(encoding="utf-8"))
            paths = doc.get("paths", {})
            for method, path in expected_ops:
                assert path in paths, f"{path} missing from {openapi_path}"
                assert method in paths[path], f"{method.upper()} {path} missing from {openapi_path}"


class TestReportResponseFiveInlineArrays:
    """AC-6: ProductionAchievementReportResponse's json-schema block lists
    all 5 inline arrays (data-shape-contract.md §3.28.4)."""

    def test_report_response_schema_lists_five_inline_arrays(self):
        content = _API_CONTRACT_PATH.read_text(encoding="utf-8")
        start = content.index("### ProductionAchievementReportResponse")
        end = content.index("### ProductionAchievementJobAccepted", start)
        block = content[start:end]

        for array_name in (
            "spec_workcenter_map",
            "targets_map",
            "package_lf_map",
            "workcenter_merge_map",
            "plan_map",
        ):
            assert f'"{array_name}"' in block, (
                f"{array_name!r} missing from ProductionAchievementReportResponse "
                "json-schema block"
            )

    def test_package_lf_map_and_workcenter_merge_map_required_fields_differ_in_name_only(self):
        """Sanity check the 2 D1/D2 inline arrays have distinct field names
        (raw_package_lf/merged_group vs raw_workcenter_group/
        merged_workcenter_group) -- guards against an accidental copy-paste
        that reuses one array's field names for the other."""
        content = _API_CONTRACT_PATH.read_text(encoding="utf-8")
        start = content.index("### ProductionAchievementReportResponse")
        end = content.index("### ProductionAchievementJobAccepted", start)
        block = content[start:end]
        assert '"raw_package_lf"' in block and '"merged_group"' in block
        assert '"raw_workcenter_group"' in block and '"merged_workcenter_group"' in block

    def test_openapi_report_response_schema_has_five_array_properties(self):
        if not _OPENAPI_PATH.exists():
            pytest.skip("contracts/openapi.json not found -- run cdd-kit openapi export first")
        doc = json.loads(_OPENAPI_PATH.read_text(encoding="utf-8"))
        schema = doc.get("components", {}).get("schemas", {}).get(
            "ProductionAchievementReportResponse"
        )
        assert schema is not None, "ProductionAchievementReportResponse missing from openapi.json components"
        data_props = schema.get("properties", {}).get("data", {}).get("properties", {})
        for array_name in (
            "spec_workcenter_map", "targets_map", "package_lf_map",
            "workcenter_merge_map", "plan_map",
        ):
            assert array_name in data_props, f"{array_name!r} missing from openapi.json's data properties"


class TestSchemaVersionBumpRecorded:
    """AC-1/AC-6: the _PA_SPOOL_SCHEMA_VERSION 1->2 bump is recorded in
    api-contract.md's Compatibility Notes (breaking parquet-schema change)."""

    def test_schema_version_bump_recorded_in_compatibility_notes(self):
        content = _API_CONTRACT_PATH.read_text(encoding="utf-8")
        assert "production-achievement-overhaul" in content
        idx = content.index("production-achievement-overhaul (2026-07-14)")
        note = content[idx:idx + 3000]
        assert "_PA_SPOOL_SCHEMA_VERSION" in note
        assert "1" in note and "2" in note
        assert "PACKAGE_LF" in note


class TestSixNewResponseSchemas:
    """AC-6: the 6 new response schemas referenced by design.md are defined
    as typed (not prose) schema sections in api-contract.md."""

    # NOTE: ProductionAchievementDailyPlanRow (originally in this list) was
    # removed by production-achievement-oracle-plan-source alongside the
    # daily-plans endpoints it backed -- see api-contract.md Compatibility Notes.
    @pytest.mark.parametrize(
        "schema_name",
        [
            "ProductionAchievementPackageLfMapRow",
            "ProductionAchievementWorkcenterMergeMapRow",
            "ProductionAchievementKnownPackageLfValuesResponse",
            "ProductionAchievementKnownWorkcenterGroupsResponse",
        ]
    )
    def test_schema_section_present(self, schema_name):
        content = _API_CONTRACT_PATH.read_text(encoding="utf-8")
        assert f"### {schema_name}" in content, f"Missing ## {schema_name} schema section"

    def test_report_response_is_the_sixth_redefined_schema(self):
        """ProductionAchievementReportResponse is the 6th schema referenced
        by this change -- it is REDEFINED in place (not a new section)."""
        content = _API_CONTRACT_PATH.read_text(encoding="utf-8")
        assert "### ProductionAchievementReportResponse" in content
        assert "redefined in place" in content.lower() or "redefined by" in content.lower()
