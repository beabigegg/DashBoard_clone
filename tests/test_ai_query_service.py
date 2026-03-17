# -*- coding: utf-8 -*-
"""Unit tests for ai_query_service module.

All external dependencies (LLM HTTP calls, service functions) are mocked
so these tests run entirely in isolation without network or DB access.
"""

import unittest
from unittest.mock import MagicMock, patch

import requests

import mes_dashboard.services.ai_query_service as svc


class TestCallLlmText(unittest.TestCase):
    """Tests for _call_llm_text()."""

    @patch("mes_dashboard.services.ai_query_service.requests.post")
    def test_returns_content_text(self, mock_post):
        """_call_llm_text must return raw text without JSON parsing."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "這是自然語言回答"}}]
        }
        mock_post.return_value = mock_response

        result = svc._call_llm_text([{"role": "user", "content": "test"}])
        self.assertEqual(result, "這是自然語言回答")

    @patch("mes_dashboard.services.ai_query_service.requests.post")
    def test_fallback_to_reasoning_content(self, mock_post):
        """_call_llm_text must fall back to reasoning_content if content is empty."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "", "reasoning_content": "推理文字"}}]
        }
        mock_post.return_value = mock_response

        result = svc._call_llm_text([{"role": "user", "content": "test"}])
        self.assertEqual(result, "推理文字")


class TestSummarizeForLlm(unittest.TestCase):
    """Tests for _summarize_for_llm()."""

    def test_pareto_full(self):
        """Pareto data under max_chars must be returned in full."""
        data = {"categories": ["A", "B"], "values": [10, 5]}
        result = svc._summarize_for_llm("reject_reason_pareto", data)
        self.assertIn("A", result)
        self.assertIn("10", result)

    def test_trend_truncation(self):
        """Trend data with > 30 points must be truncated to head/tail + stats."""
        items = [{"date": f"2026-01-{i:02d}", "reject_rate": float(i)} for i in range(1, 35)]
        result = svc._summarize_for_llm("reject_trend", items)
        self.assertIn("前5筆", result)
        self.assertIn("後5筆", result)
        self.assertIn("統計", result)

    def test_trend_no_truncation_under_30(self):
        """Trend data with <= 30 points must be returned as-is."""
        items = [{"date": f"2026-01-{i:02d}", "reject_rate": 1.0} for i in range(1, 10)]
        result = svc._summarize_for_llm("reject_trend", items)
        self.assertNotIn("前5筆", result)

    def test_heatmap_top10(self):
        """Heatmap must include top-10 cells."""
        data = {
            "xAxis": ["A", "B"],
            "yAxis": ["X", "Y"],
            "data": [[0, 0, 100], [0, 1, 50], [1, 0, 200]],
        }
        result = svc._summarize_for_llm("wip_matrix", data)
        self.assertIn("top10_cells", result)

    def test_table_truncation(self):
        """Table data with > 10 rows must include first 10 + total count."""
        rows = [{"id": i, "val": i * 2} for i in range(20)]
        result = svc._summarize_for_llm("reject_lot_list", rows)
        self.assertIn("共", result)
        self.assertIn("20", result)

    def test_kpi_full(self):
        """KPI data must be returned in full."""
        data = [{"label": "總批次", "value": 100}]
        result = svc._summarize_for_llm("wip_summary", data)
        self.assertIn("總批次", result)

    def test_none_returns_placeholder(self):
        """None chart_data must return a placeholder string."""
        result = svc._summarize_for_llm("reject_reason_pareto", None)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_fallback_unknown_chart_type(self):
        """Unknown chart type must fall back to json.dumps truncation."""
        data = {"foo": "bar"}
        result = svc._summarize_for_llm("unknown_fn", data)
        self.assertIn("bar", result)


class TestProcessQueryLLMErrors(unittest.TestCase):
    """Tests for LLM connectivity error propagation in process_query()."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_llm_timeout_raises_timeout(self, mock_call_llm):
        """requests.Timeout from Round 1 _call_llm must surface as TimeoutError."""
        mock_call_llm.side_effect = requests.Timeout("timed out")

        with self.assertRaises(TimeoutError):
            svc.process_query("question")

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_llm_connection_error_raises_connection_error(self, mock_call_llm):
        """requests.ConnectionError from Round 1 _call_llm must surface as ConnectionError."""
        mock_call_llm.side_effect = requests.ConnectionError("connection refused")

        with self.assertRaises(ConnectionError):
            svc.process_query("question")


class TestProcessQueryNullIntent(unittest.TestCase):
    """Tests for process_query() when LLM returns null function intent."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_null_intent_returns_answer(self, mock_call_llm):
        """When Round 1 returns function=None, result must have answer set and no chart_data."""
        mock_call_llm.return_value = {
            "function": None,
            "explanation": "無法理解",
        }

        result = svc.process_query("gibberish")

        self.assertEqual(result["answer"], "無法理解")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["query_used"])
        self.assertNotIn("conversation_id", result)


class TestProcessQueryValidIntent(unittest.TestCase):
    """Tests for process_query() happy path with a valid LLM intent."""

    @patch("mes_dashboard.services.ai_query_service._call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_valid_intent_dispatches_service(
        self,
        mock_call_llm,
        mock_get_svc,
        mock_call_llm_text,
    ):
        """Valid 3-round pipeline must dispatch service and return query_used + answer."""
        # R1 returns intent, R2 returns params
        mock_call_llm.side_effect = [
            {"function": "reject_spike_alerts", "explanation": "查詢不良突增"},
            {"params": {"detector": "reject"}},
        ]
        mock_service_fn = MagicMock(return_value={"items": [{"detector": "reject", "severity": "warning"}]})
        mock_get_svc.return_value = mock_service_fn
        mock_call_llm_text.return_value = "近期發現 1 筆不良突增異常。"

        result = svc.process_query("查詢最近不良突增")

        self.assertEqual(result["query_used"], "reject_spike_alerts")
        self.assertEqual(result["answer"], "近期發現 1 筆不良突增異常。")
        self.assertNotIn("conversation_id", result)
        self.assertNotIn("round", result)
        mock_service_fn.assert_called_once_with(detector="reject")

    @patch("mes_dashboard.services.ai_query_service._call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_no_conversation_id_in_response(
        self, mock_call_llm, mock_get_svc, mock_call_llm_text
    ):
        """Response must not contain conversation_id, round, or max_rounds."""
        mock_call_llm.side_effect = [
            {"function": "reject_spike_alerts", "explanation": "查詢"},
            {"params": {"detector": "reject"}},
        ]
        mock_get_svc.return_value = MagicMock(return_value={"items": []})
        mock_call_llm_text.return_value = "無異常。"

        result = svc.process_query("查詢")

        self.assertNotIn("conversation_id", result)
        self.assertNotIn("round", result)
        self.assertNotIn("max_rounds", result)


class TestRound3Fallback(unittest.TestCase):
    """Round 3 failure must not propagate — chart_data still returned."""

    @patch("mes_dashboard.services.ai_query_service._call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_round3_failure_returns_fallback_answer(
        self, mock_call_llm, mock_get_svc, mock_call_llm_text
    ):
        """When Round 3 raises, answer must be the fallback text and chart_data intact."""
        mock_call_llm.side_effect = [
            {"function": "reject_spike_alerts", "explanation": "查詢"},
            {"params": {"detector": "reject"}},
        ]
        mock_service_fn = MagicMock(return_value={"items": [{"id": 1}]})
        mock_get_svc.return_value = mock_service_fn
        mock_call_llm_text.side_effect = RuntimeError("LLM R3 failed")

        result = svc.process_query("查詢")

        self.assertEqual(result["answer"], "查詢完成，請參考圖表。")
        self.assertIsNotNone(result["chart_data"])
        self.assertEqual(result["query_used"], "reject_spike_alerts")
