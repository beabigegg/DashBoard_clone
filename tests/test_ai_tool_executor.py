# -*- coding: utf-8 -*-
"""Unit tests for ai_tool_executor.py"""
import unittest
from unittest.mock import patch, MagicMock

from mes_dashboard.services import ai_tool_executor as exe


class TestExecuteToolUnknown(unittest.TestCase):
    def test_unknown_tool_returns_error(self):
        result = exe.execute_tool("nonexistent_tool_xyz", {})
        self.assertFalse(result["success"])
        self.assertIn("nonexistent_tool_xyz", result["error"])
        self.assertIsNone(result["chart_data"])


class TestExecuteToolYaml(unittest.TestCase):
    @patch("mes_dashboard.services.ai_tool_executor.get_service_function")
    @patch("mes_dashboard.services.ai_tool_executor.normalize_chart_data")
    @patch("mes_dashboard.services.ai_tool_executor.summarize_for_llm")
    def test_yaml_tool_success(self, mock_summarize, mock_normalize, mock_get_svc):
        """Valid YAML tool call returns success with result_summary and chart_data."""
        mock_fn = MagicMock(return_value=[{"value": 1}])
        mock_get_svc.return_value = mock_fn
        mock_normalize.return_value = [{"value": 1}]
        mock_summarize.return_value = "summary text"

        result = exe.execute_tool("reject_summary", {
            "start_date": "2026-03-01",
            "end_date": "2026-03-18",
        })
        self.assertTrue(result["success"])
        self.assertEqual(result["result_summary"], "summary text")
        self.assertIsNone(result["error"])

    @patch("mes_dashboard.services.ai_tool_executor.get_service_function")
    def test_yaml_tool_type_error(self, mock_get_svc):
        """TypeError from service function returns structured error."""
        mock_fn = MagicMock(side_effect=TypeError("bad args"))
        mock_get_svc.return_value = mock_fn

        result = exe.execute_tool("reject_summary", {
            "start_date": "2026-03-01",
            "end_date": "2026-03-18",
        })
        self.assertFalse(result["success"])
        self.assertIn("參數錯誤", result["error"])

    def test_validation_failure_returns_error(self):
        """Missing required params without default returns validation error."""
        # reject_summary requires start_date and end_date
        result = exe.execute_tool("reject_summary", {})
        self.assertFalse(result["success"])
        self.assertIn("參數錯誤", result["error"])


class TestExecuteSearchTools(unittest.TestCase):
    def test_search_finds_matching_tools(self):
        """search_tools with a common keyword returns matching tools."""
        result = exe.execute_tool("search_tools", {"keyword": "不良"})
        self.assertTrue(result["success"])
        self.assertIn("不良", result["result_summary"])

    def test_search_no_match(self):
        """search_tools with no match returns informative message."""
        result = exe.execute_tool("search_tools", {"keyword": "xyz不存在關鍵字abc"})
        self.assertTrue(result["success"])
        self.assertIn("沒有找到", result["result_summary"])

    def test_search_missing_keyword(self):
        """search_tools without keyword returns error."""
        result = exe.execute_tool("search_tools", {})
        self.assertFalse(result["success"])


class TestExecuteQueryDatabase(unittest.TestCase):
    @patch("mes_dashboard.services.ai_query_service.process_query_text2sql")
    def test_delegates_to_text2sql(self, mock_t2s):
        mock_t2s.return_value = {"answer": "查詢結果", "chart_data": None}
        result = exe.execute_tool("query_database", {"question": "本月良率"})
        self.assertTrue(result["success"])
        self.assertIn("查詢結果", result["result_summary"])
        mock_t2s.assert_called_once_with("本月良率")

    def test_missing_question_returns_error(self):
        result = exe.execute_tool("query_database", {})
        self.assertFalse(result["success"])


class TestExecuteToolExceptionSafety(unittest.TestCase):
    @patch("mes_dashboard.services.ai_tool_executor._execute_yaml_tool")
    def test_unexpected_exception_caught(self, mock_exec):
        """Unexpected exceptions from internal handlers are caught."""
        mock_exec.side_effect = RuntimeError("something blew up")
        result = exe.execute_tool("reject_summary", {"start_date": "2026-03-01", "end_date": "2026-03-18"})
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])


if __name__ == "__main__":
    unittest.main()
