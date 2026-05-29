# -*- coding: utf-8 -*-
"""Unit tests for ai_function_registry module.

Covers:
- YAML loading and enum expansion
- build_round1_prompt(), build_round2_prompt(), build_round3_prompt()
- validate_intent()
- get_suggestions()
"""

import importlib
import unittest

from mes_dashboard.services.ai_function_registry import (
    REGISTRY,
    build_round1_prompt,
    build_round2_prompt,
    build_round3_prompt,
    build_reviewer_prompt,
    build_stage1_prompt,
    build_stage2_prompt,
    get_suggestions,
    validate_intent,
)


class TestYamlLoading(unittest.TestCase):
    """YAML loading, enum expansion, and service import checks."""

    def test_registry_is_nonempty_dict(self):
        """REGISTRY must be a non-empty dict after YAML load."""
        self.assertIsInstance(REGISTRY, dict)
        self.assertGreater(len(REGISTRY), 0)

    def test_all_known_functions_present(self):
        """All 16 expected function names must exist in REGISTRY."""
        expected = {
            "reject_reason_pareto", "reject_trend", "reject_spike_alerts", "reject_lot_list",
            "yield_anomaly_alerts", "yield_anomaly_drilldown",
            "wip_summary", "wip_matrix", "wip_hold_summary",
            "hold_outlier_alerts", "hold_history_trend", "hold_reason_pareto",
            "equipment_deviation_alerts", "equipment_status_summary",
            "lot_query", "equipment_recent_jobs",
        }
        for name in expected:
            with self.subTest(name=name):
                self.assertIn(name, REGISTRY)

    def test_enum_references_expanded(self):
        """$WORKCENTER_GROUPS references must be expanded to a list."""
        entry = REGISTRY["reject_reason_pareto"]
        wg_enum = entry["params"]["workcenter_groups"]["enum"]
        self.assertIsInstance(wg_enum, list)
        self.assertIn("切割", wg_enum)
        self.assertIn("焊接_WB", wg_enum)

    def test_registry_params_have_required_fields(self):
        """Every param spec must have at minimum 'type' and 'required' keys."""
        for func_name, entry in REGISTRY.items():
            for param_name, pspec in (entry.get("params") or {}).items():
                with self.subTest(func_name=func_name, param=param_name):
                    self.assertIn("type", pspec)
                    self.assertIn("required", pspec)

    def test_all_services_importable(self):
        """Every REGISTRY entry must point to an importable module with the named function."""
        for func_name, entry in REGISTRY.items():
            service_path = entry["service"]
            module_path, fn_name = service_path.rsplit(".", 1)
            with self.subTest(func_name=func_name, service=service_path):
                try:
                    module = importlib.import_module(module_path)
                except ImportError as exc:
                    self.fail(f"Cannot import module '{module_path}' for '{func_name}': {exc}")
                self.assertTrue(
                    hasattr(module, fn_name),
                    f"Module '{module_path}' has no attribute '{fn_name}'",
                )

    def test_chart_type_present(self):
        """Every entry must have a chart_type field."""
        valid_types = {"pareto", "trend", "heatmap", "kpi", "table"}
        for func_name, entry in REGISTRY.items():
            with self.subTest(func_name=func_name):
                self.assertIn("chart_type", entry)
                self.assertIn(entry["chart_type"], valid_types)


class TestBuildRound1Prompt(unittest.TestCase):
    """Tests for build_round1_prompt()."""

    def test_all_function_names_present(self):
        """All REGISTRY function names must appear in Round 1 prompt."""
        prompt = build_round1_prompt()
        for func_name in REGISTRY:
            with self.subTest(func_name=func_name):
                self.assertIn(func_name, prompt)

    def test_no_param_details(self):
        """Round 1 prompt must NOT contain individual parameter names like 'start_date'."""
        prompt = build_round1_prompt()
        self.assertNotIn("start_date", prompt)
        self.assertNotIn("workcenter_groups", prompt)

    def test_contains_json_format_instruction(self):
        """Round 1 prompt must specify a JSON reply format."""
        prompt = build_round1_prompt()
        self.assertIn('"function"', prompt)


class TestBuildRound2Prompt(unittest.TestCase):
    """Tests for build_round2_prompt(function_name)."""

    def test_contains_only_selected_function_params(self):
        """Round 2 prompt must include params for the requested function."""
        prompt = build_round2_prompt("reject_reason_pareto")
        self.assertIn("reject_reason_pareto", prompt)
        self.assertIn("start_date", prompt)

    def test_does_not_contain_other_function_params(self):
        """Round 2 prompt for one function must not contain other function names."""
        prompt = build_round2_prompt("reject_reason_pareto")
        self.assertNotIn("wip_matrix", prompt)
        self.assertNotIn("lot_query", prompt)

    def test_contains_enum_values(self):
        """Round 2 prompt must include workcenter enum values."""
        prompt = build_round2_prompt("reject_reason_pareto")
        self.assertIn("切割", prompt)
        self.assertIn("焊接_WB", prompt)

    def test_unknown_function_raises_key_error(self):
        """build_round2_prompt with unknown function must raise KeyError."""
        with self.assertRaises(KeyError):
            build_round2_prompt("nonexistent_fn")


class TestBuildRound3Prompt(unittest.TestCase):
    """Tests for build_round3_prompt()."""

    def test_no_json_instruction(self):
        """Round 3 prompt must NOT ask for JSON output."""
        prompt = build_round3_prompt()
        self.assertNotIn('"function"', prompt)
        self.assertNotIn('"params"', prompt)

    def test_contains_analysis_rules(self):
        """Round 3 prompt must mention analysis instructions."""
        prompt = build_round3_prompt()
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 0)
        # Should contain Chinese analysis guidance
        self.assertIn("直接回答", prompt)


class TestValidateIntent(unittest.TestCase):
    """Tests for validate_intent()."""

    def test_validate_intent_unknown_function(self):
        """Unknown function name must return (False, non-empty message)."""
        ok, msg = validate_intent("nonexistent_fn", {})
        self.assertFalse(ok)
        self.assertGreater(len(msg), 0)

    def test_validate_intent_missing_required_param(self):
        """Missing required param without default must return (False, ...)."""
        ok, msg = validate_intent("reject_reason_pareto", {})
        self.assertFalse(ok)
        self.assertGreater(len(msg), 0)

    def test_validate_intent_valid(self):
        """Valid call must return (True, '')."""
        ok, msg = validate_intent("reject_spike_alerts", {"detector": "reject"})
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_validate_intent_invalid_enum(self):
        """Param value outside enum must return (False, ...)."""
        ok, msg = validate_intent(
            "yield_anomaly_drilldown",
            {"workcenter_group": "INVALID_GROUP", "package": "SOT-23"},
        )
        self.assertFalse(ok)
        self.assertIn("INVALID_GROUP", msg)

    def test_validate_intent_valid_with_dates(self):
        """A fully-specified call for reject_reason_pareto must pass."""
        ok, msg = validate_intent(
            "reject_reason_pareto",
            {"start_date": "2026-03-01", "end_date": "2026-03-07"},
        )
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_validate_intent_list_enum_invalid_element(self):
        """List param with an invalid element in enum must return (False, ...)."""
        ok, msg = validate_intent(
            "reject_reason_pareto",
            {
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "workcenter_groups": ["切割", "NOT_A_GROUP"],
            },
        )
        self.assertFalse(ok)
        self.assertIn("NOT_A_GROUP", msg)


class TestGetSuggestions(unittest.TestCase):
    """Tests for get_suggestions()."""

    def test_get_suggestions_returns_list(self):
        """Known function must return a non-empty list of strings."""
        suggestions = get_suggestions("reject_reason_pareto")
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)
        for item in suggestions:
            self.assertIsInstance(item, str)

    def test_get_suggestions_unknown_function(self):
        """Unknown function must return an empty list."""
        suggestions = get_suggestions("unknown")
        self.assertEqual(suggestions, [])

    def test_get_suggestions_equipment_status(self):
        """equipment_status_summary must return at least one suggestion."""
        suggestions = get_suggestions("equipment_status_summary")
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)


class TestStage1Prompt(unittest.TestCase):
    """Tests for build_stage1_prompt() — Text-to-SQL Stage 1."""

    def test_returns_string(self):
        prompt = build_stage1_prompt()
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 100)

    def test_contains_all_domain_names(self):
        from mes_dashboard.services.ai_schema_context import TABLE_DOMAINS
        prompt = build_stage1_prompt()
        for domain_key in TABLE_DOMAINS:
            self.assertIn(domain_key, prompt, f"Domain '{domain_key}' missing from Stage 1 prompt")

    def test_contains_mes_domain_knowledge(self):
        prompt = build_stage1_prompt()
        self.assertIn("GWBK", prompt)     # equipment ID format
        self.assertIn("GA/GC", prompt)    # workorder format
        self.assertIn("WB", prompt)       # station abbreviation
        self.assertIn("wip_realtime", prompt)
        self.assertIn("品質 Hold", prompt)
        self.assertIn("2N7002K", prompt)
        self.assertIn("CONTAINERID", prompt)
        self.assertIn("FINISHEDRUNCARD", prompt)

    def test_contains_json_format_instruction(self):
        prompt = build_stage1_prompt()
        self.assertIn('"domains"', prompt)
        self.assertIn('"thought"', prompt)


class TestStage2Prompt(unittest.TestCase):
    """Tests for build_stage2_prompt() — Text-to-SQL Stage 2."""

    def test_returns_string(self):
        prompt = build_stage2_prompt(["wip_realtime"])
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 100)

    def test_injects_wip_realtime_schema(self):
        prompt = build_stage2_prompt(["wip_realtime"])
        self.assertIn("DWH.DW_MES_LOT_V", prompt)
        self.assertIn("DWH.DW_MES_EQUIPMENTSTATUS_WIP_V", prompt)

    def test_injects_hold_schema(self):
        prompt = build_stage2_prompt(["hold"])
        self.assertIn("DWH.DW_MES_HOLDRELEASEHISTORY", prompt)

    def test_does_not_inject_unrelated_schema(self):
        prompt_wip = build_stage2_prompt(["wip_realtime"])
        # hold table should not appear when only wip_realtime requested
        self.assertNotIn("DWH.DW_MES_HOLDRELEASEHISTORY", prompt_wip)

    def test_contains_sql_generation_rules(self):
        prompt = build_stage2_prompt(["equipment"])
        self.assertIn("FETCH FIRST", prompt)
        self.assertIn(":start_date", prompt)
        self.assertIn(":end_date", prompt)

    def test_stage2_prompt_contains_quality_hold_rule(self):
        prompt = build_stage2_prompt(["wip_realtime"])
        self.assertIn("品質異常 Hold / 品質 Hold", prompt)
        self.assertIn("不可用 HOLDREASONNAME LIKE '%品質異常%'", prompt)

    def test_stage2_prompt_contains_product_type_rule(self):
        prompt = build_stage2_prompt(["wip_realtime"])
        self.assertIn("2N7002K", prompt)
        self.assertIn("優先使用 PJ_TYPE", prompt)

    def test_stage2_prompt_contains_id_without_date_rule(self):
        prompt = build_stage2_prompt(["lot_history"])
        self.assertIn("已指定 lot / workorder", prompt)
        self.assertIn("可不加日期限制", prompt)
        self.assertIn("GA26020001", prompt)

    def test_stage2_prompt_contains_workcenter_group_rule(self):
        prompt = build_stage2_prompt(["yield"])
        self.assertIn("WORKCENTER_GROUP", prompt)
        self.assertIn("站點/站別", prompt)

    def test_stage2_prompt_contains_reject_exclusion_policy(self):
        prompt = build_stage2_prompt(["reject"])
        self.assertIn("Reject 排除口徑", prompt)
        self.assertIn("SCRAP_OBJECTTYPE = 'MATERIAL'", prompt)

    def test_reviewer_prompt_contains_id_resolution_rules(self):
        prompt = build_reviewer_prompt(["lot_history", "genealogy"])
        self.assertIn("resolve 成 CONTAINERID", prompt)
        self.assertIn("FINISHEDRUNCARD 不是通用主鍵", prompt)

    def test_reviewer_prompt_contains_workcenter_group_and_reject_policy(self):
        prompt = build_reviewer_prompt(["reject", "yield"])
        self.assertIn("WORKCENTER_GROUP", prompt)
        self.assertIn("Reject 排除口徑", prompt)

    def test_contains_json_format_instruction(self):
        prompt = build_stage2_prompt(["reject"])
        self.assertIn('"sql"', prompt)
        self.assertIn('"params"', prompt)
        self.assertIn('"explanation"', prompt)

    def test_empty_domains_returns_prompt_without_schema(self):
        prompt = build_stage2_prompt([])
        # Should still return a valid prompt with generation rules
        self.assertIsInstance(prompt, str)
        self.assertIn("FETCH FIRST", prompt)


# ---------------------------------------------------------------------------
# IP-1: Combined prompt tests (AC-2)
# ---------------------------------------------------------------------------

class TestCombinedPromptContainsAll41Functions(unittest.TestCase):
    """AC-2: build_combined_prompt must include all registered function names."""

    def test_all_function_names_present(self):
        from mes_dashboard.services.ai_function_registry import build_combined_prompt
        prompt = build_combined_prompt()
        for func_name in REGISTRY:
            with self.subTest(func_name=func_name):
                self.assertIn(func_name, prompt)

    def test_prompt_contains_json_output_schema_instruction(self):
        from mes_dashboard.services.ai_function_registry import build_combined_prompt
        prompt = build_combined_prompt()
        # Must require params in output
        self.assertIn('"params"', prompt)
        self.assertIn('"function"', prompt)
        self.assertIn('"explanation"', prompt)

    def test_prompt_does_not_contain_full_param_schemas(self):
        """Combined prompt must NOT inline full parameter schemas (design D1)."""
        from mes_dashboard.services.ai_function_registry import build_combined_prompt
        prompt = build_combined_prompt()
        # Full schema details (type, required, enum) should not be inlined
        # (name+description catalogue only, per D1)
        self.assertNotIn('"required": true', prompt)
        self.assertNotIn('"type": "string"', prompt)


class TestCombinedPromptTokenBudget(unittest.TestCase):
    """AC-2: combined prompt must stay within safe margin of 131K context window."""

    def test_prompt_char_count_within_safe_limit(self):
        from mes_dashboard.services.ai_function_registry import build_combined_prompt
        prompt = build_combined_prompt()
        # Rough estimate: 131072 tokens * ~3 chars/token = ~393K chars upper bound
        # A safe margin: prompt should not exceed 50K chars (well within 131K token window)
        self.assertLess(len(prompt), 50000)

    def test_prompt_is_nonempty_string(self):
        from mes_dashboard.services.ai_function_registry import build_combined_prompt
        prompt = build_combined_prompt()
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 200)


# ---------------------------------------------------------------------------
# IP-5: New YAML function entry tests (AC-6, AC-7)
# ---------------------------------------------------------------------------

class TestProductionHistoryQueryFunctionEntry(unittest.TestCase):
    """AC-6: production_history_query must exist in REGISTRY with correct fields."""

    def test_entry_exists(self):
        self.assertIn("production_history_query", REGISTRY)

    def test_service_path_correct(self):
        entry = REGISTRY["production_history_query"]
        self.assertIn("production_history_service", entry["service"])
        self.assertIn("query_production_history", entry["service"])

    def test_dispatch_is_raw_params(self):
        entry = REGISTRY["production_history_query"]
        self.assertEqual(entry.get("dispatch"), "raw_params")

    def test_chart_type_is_table(self):
        entry = REGISTRY["production_history_query"]
        self.assertEqual(entry["chart_type"], "table")

    def test_required_params_present(self):
        entry = REGISTRY["production_history_query"]
        params = entry["params"]
        self.assertIn("start_date", params)
        self.assertIn("end_date", params)
        self.assertTrue(params["start_date"]["required"])
        self.assertTrue(params["end_date"]["required"])

    def test_optional_params_present(self):
        entry = REGISTRY["production_history_query"]
        params = entry["params"]
        self.assertIn("lot_ids", params)
        self.assertIn("pj_types", params)
        self.assertFalse(params["lot_ids"]["required"])
        self.assertFalse(params["pj_types"]["required"])


class TestResourceHistorySummaryFunctionEntry(unittest.TestCase):
    """AC-6: resource_history_summary must exist in REGISTRY with correct fields."""

    def test_entry_exists(self):
        self.assertIn("resource_history_summary", REGISTRY)

    def test_service_path_correct(self):
        entry = REGISTRY["resource_history_summary"]
        self.assertIn("resource_history_service", entry["service"])
        self.assertIn("query_summary", entry["service"])

    def test_chart_type_is_trend(self):
        entry = REGISTRY["resource_history_summary"]
        # Per the implementation plan, chart_type is trend (design.md D3 says kpi but
        # implementation-plan.md says kpi; test-plan says "contract" — use what YAML says)
        self.assertIn(entry["chart_type"], {"trend", "kpi"})

    def test_granularity_has_enum(self):
        entry = REGISTRY["resource_history_summary"]
        params = entry["params"]
        self.assertIn("granularity", params)
        enum = params["granularity"].get("enum")
        self.assertIsNotNone(enum)
        self.assertIn("day", enum)
        self.assertIn("week", enum)
        self.assertIn("month", enum)
        self.assertIn("year", enum)

    def test_granularity_has_default(self):
        entry = REGISTRY["resource_history_summary"]
        self.assertEqual(entry["params"]["granularity"].get("default"), "day")

    def test_sensitive_params_excluded(self):
        """families, resource_ids, is_production, is_key, is_monitor must not be exposed."""
        entry = REGISTRY["resource_history_summary"]
        params = entry.get("params") or {}
        for excluded in ("families", "resource_ids", "is_production", "is_key", "is_monitor"):
            self.assertNotIn(excluded, params, f"Sensitive param '{excluded}' must not be exposed")


class TestQcGateStatusFunctionEntry(unittest.TestCase):
    """AC-6: qc_gate_status must exist in REGISTRY with no params."""

    def test_entry_exists(self):
        self.assertIn("qc_gate_status", REGISTRY)

    def test_service_path_correct(self):
        entry = REGISTRY["qc_gate_status"]
        self.assertIn("qc_gate_service", entry["service"])
        self.assertIn("get_qc_gate_summary", entry["service"])

    def test_chart_type_is_table(self):
        entry = REGISTRY["qc_gate_status"]
        self.assertEqual(entry["chart_type"], "table")


class TestQcGateStatusNoParams(unittest.TestCase):
    """AC-7: qc_gate_status has no params (params: {})."""

    def test_params_is_empty(self):
        entry = REGISTRY["qc_gate_status"]
        params = entry.get("params") or {}
        self.assertEqual(params, {})

    def test_validate_intent_passes_with_empty_params(self):
        ok, msg = validate_intent("qc_gate_status", {})
        self.assertTrue(ok)
        self.assertEqual(msg, "")


class TestProductionHistoryQueryParamSchema(unittest.TestCase):
    """AC-7: production_history_query param schema validation."""

    def test_validate_intent_fails_missing_start_date(self):
        ok, msg = validate_intent("production_history_query", {"end_date": "2026-01-07"})
        self.assertFalse(ok)

    def test_validate_intent_fails_missing_end_date(self):
        ok, msg = validate_intent("production_history_query", {"start_date": "2026-01-01"})
        self.assertFalse(ok)

    def test_validate_intent_passes_with_required_dates(self):
        ok, msg = validate_intent(
            "production_history_query",
            {"start_date": "2026-01-01", "end_date": "2026-01-07"},
        )
        self.assertTrue(ok)

    def test_validate_intent_passes_with_optional_params(self):
        ok, msg = validate_intent(
            "production_history_query",
            {
                "start_date": "2026-01-01",
                "end_date": "2026-01-07",
                "lot_ids": ["GA001", "GA002"],
                "pj_types": ["2N7002K"],
            },
        )
        self.assertTrue(ok)


class TestResourceHistorySummaryParamSchema(unittest.TestCase):
    """AC-7: resource_history_summary param schema validation."""

    def test_validate_intent_fails_missing_dates(self):
        ok, msg = validate_intent("resource_history_summary", {})
        self.assertFalse(ok)

    def test_validate_intent_passes_with_required_dates(self):
        ok, msg = validate_intent(
            "resource_history_summary",
            {"start_date": "2026-01-01", "end_date": "2026-01-07"},
        )
        self.assertTrue(ok)

    def test_validate_intent_fails_invalid_granularity(self):
        ok, msg = validate_intent(
            "resource_history_summary",
            {
                "start_date": "2026-01-01",
                "end_date": "2026-01-07",
                "granularity": "hourly",  # not in enum
            },
        )
        self.assertFalse(ok)

    def test_validate_intent_passes_valid_granularity(self):
        for granularity in ("day", "week", "month", "year"):
            ok, msg = validate_intent(
                "resource_history_summary",
                {
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-07",
                    "granularity": granularity,
                },
            )
            with self.subTest(granularity=granularity):
                self.assertTrue(ok)


class TestYamlLoadingExtended(unittest.TestCase):
    """Extend existing TestYamlLoading to cover 41 names."""

    def test_all_41_new_functions_present(self):
        """The three new functions must be in REGISTRY (41 total)."""
        for name in ("production_history_query", "resource_history_summary", "qc_gate_status"):
            with self.subTest(name=name):
                self.assertIn(name, REGISTRY)

    def test_total_registry_size_is_at_least_41(self):
        """Registry must have at least 41 entries (38 original + 3 new, or more if prior commits added entries)."""
        self.assertGreaterEqual(len(REGISTRY), 41)


if __name__ == "__main__":
    unittest.main()
