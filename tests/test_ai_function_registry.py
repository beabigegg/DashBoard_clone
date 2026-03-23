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

    def test_reviewer_prompt_contains_id_resolution_rules(self):
        prompt = build_reviewer_prompt(["lot_history", "genealogy"])
        self.assertIn("resolve 成 CONTAINERID", prompt)
        self.assertIn("FINISHEDRUNCARD 不是通用主鍵", prompt)

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


if __name__ == "__main__":
    unittest.main()
