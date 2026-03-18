# -*- coding: utf-8 -*-
"""Unit tests for ai_agent_loop.py"""
import unittest
from unittest.mock import patch, MagicMock

from mes_dashboard.services import ai_agent_loop as loop


def _make_llm_text_side_effect(*responses):
    """Return a side_effect list for call_llm_text mock."""
    return list(responses)


class TestSingleToolCall(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    @patch("mes_dashboard.services.ai_agent_loop.execute_tool")
    def test_single_tool_call(self, mock_execute, mock_llm):
        """LLM calls one tool in Round 1, then returns final answer in Round 2."""
        mock_llm.side_effect = [
            '<tool_call>{"name": "reject_summary", "arguments": {"start_date": "2026-03-01", "end_date": "2026-03-18"}}</tool_call>',
            "今日不良率為 2.5%，屬正常範圍。",
        ]
        mock_execute.return_value = {
            "success": True,
            "result_summary": "不良率 2.5%",
            "chart_data": [{"x": "2026-03-01", "y": 2.5}],
            "error": None,
        }

        result = loop.process_agent_turn("今天不良率多少？")

        self.assertEqual(result["answer"], "今日不良率為 2.5%，屬正常範圍。")
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(len(result["tool_trace"]), 1)
        self.assertEqual(result["tool_trace"][0]["function"], "reject_summary")
        self.assertIsNotNone(result["chart_data"])


class TestMultipleToolCalls(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    @patch("mes_dashboard.services.ai_agent_loop.execute_tool")
    def test_two_tools_across_rounds(self, mock_execute, mock_llm):
        """LLM requests two tools across rounds and produces unified answer."""
        mock_llm.side_effect = [
            '<tool_call>{"name": "reject_trend", "arguments": {"start_date": "2026-03-01", "end_date": "2026-03-18"}}</tool_call>\n<tool_call>{"name": "reject_reason_pareto", "arguments": {"start_date": "2026-03-01", "end_date": "2026-03-18"}}</tool_call>',
            "趨勢上升，主要不良原因是 A。",
        ]
        mock_execute.return_value = {
            "success": True,
            "result_summary": "data",
            "chart_data": [{"x": 1}],
            "error": None,
        }

        result = loop.process_agent_turn("A 站不良率趨勢和前三大不良原因")

        self.assertEqual(result["answer"], "趨勢上升，主要不良原因是 A。")
        self.assertEqual(len(result["tool_trace"]), 2)
        self.assertEqual(mock_execute.call_count, 2)


class TestNoToolCall(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    def test_no_tool_call_returns_direct_answer(self, mock_llm):
        """LLM answers without any tool call → single round response.

        Note: per spec Decision 4, if the answer contains '?' and no tools were
        executed, needs_clarification is True. This is intentional for MES queries.
        """
        mock_llm.return_value = "MES 是製造執行系統，負責管理生產線各站別資料。"

        result = loop.process_agent_turn("MES 是什麼？")

        self.assertEqual(result["answer"], "MES 是製造執行系統，負責管理生產線各站別資料。")
        self.assertFalse(result["needs_clarification"])  # no question mark in answer
        self.assertEqual(len(result["tool_trace"]), 0)
        mock_llm.assert_called_once()


class TestClarification(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    def test_needs_clarification_set_when_question_no_tools(self, mock_llm):
        """No tool calls + response contains question mark → needs_clarification=True."""
        mock_llm.return_value = "請問您想查哪個站點的不良率？"

        result = loop.process_agent_turn("不良率多少？")

        self.assertTrue(result["needs_clarification"])
        self.assertEqual(len(result["tool_trace"]), 0)

    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    @patch("mes_dashboard.services.ai_agent_loop.execute_tool")
    def test_no_clarification_when_tools_executed(self, mock_execute, mock_llm):
        """If tools were executed, needs_clarification=False even if answer has '?'."""
        mock_llm.side_effect = [
            '<tool_call>{"name": "reject_summary", "arguments": {"start_date": "2026-03-01", "end_date": "2026-03-18"}}</tool_call>',
            "不良率 2%，是否需要更多分析？",
        ]
        mock_execute.return_value = {
            "success": True,
            "result_summary": "2%",
            "chart_data": None,
            "error": None,
        }

        result = loop.process_agent_turn("今天不良率？")
        self.assertFalse(result["needs_clarification"])


class TestMaxRounds(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    @patch("mes_dashboard.services.ai_agent_loop.execute_tool")
    def test_max_rounds_terminates_loop(self, mock_execute, mock_llm):
        """Loop stops after MAX_ROUNDS even if LLM keeps calling tools."""
        # Always respond with a tool call
        mock_llm.return_value = '<tool_call>{"name": "reject_summary", "arguments": {"start_date": "2026-03-01", "end_date": "2026-03-18"}}</tool_call>'
        mock_execute.return_value = {
            "success": True,
            "result_summary": "data",
            "chart_data": None,
            "error": None,
        }

        result = loop.process_agent_turn("查不良率")

        # LLM called MAX_ROUNDS times
        self.assertEqual(mock_llm.call_count, loop.MAX_ROUNDS)
        self.assertIn("上限", result["answer"])


class TestDuplicateCallDedup(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    @patch("mes_dashboard.services.ai_agent_loop.execute_tool")
    def test_duplicate_tool_call_skipped(self, mock_execute, mock_llm):
        """Same tool+args in Round 2 should be skipped (not executed again)."""
        tool_call = '<tool_call>{"name": "reject_summary", "arguments": {"start_date": "2026-03-01", "end_date": "2026-03-18"}}</tool_call>'
        mock_llm.side_effect = [
            tool_call,
            tool_call,   # same call again → should be skipped
            "最終回答",
        ]
        mock_execute.return_value = {
            "success": True,
            "result_summary": "data",
            "chart_data": None,
            "error": None,
        }

        result = loop.process_agent_turn("查不良率")

        # execute_tool should only be called once despite two identical tool_calls
        self.assertEqual(mock_execute.call_count, 1)
        self.assertEqual(result["answer"], "最終回答")


class TestMalformedToolCall(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    @patch("mes_dashboard.services.ai_agent_loop.execute_tool")
    def test_malformed_json_skipped(self, mock_execute, mock_llm):
        """Malformed tool_call JSON is skipped, loop continues normally."""
        mock_llm.side_effect = [
            '<tool_call>{"name": "reject_summary", INVALID JSON}</tool_call>',
            "回答：無法查詢。",
        ]

        result = loop.process_agent_turn("不良率多少？")

        # execute_tool should not be called (JSON parse failed)
        mock_execute.assert_not_called()
        self.assertIn("回答", result["answer"])


class TestClarificationSuggestions(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    def test_suggestions_populated_on_clarification(self, mock_llm):
        """When needs_clarification=True, suggestions should contain context-relevant items."""
        mock_llm.return_value = "請問您想查哪個站點的不良率？"

        result = loop.process_agent_turn("不良率多少？")

        self.assertTrue(result["needs_clarification"])
        self.assertGreater(len(result["suggestions"]), 0)
        # At least one suggestion should relate to "不良"
        self.assertTrue(any("不良" in s for s in result["suggestions"]))

    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    def test_suggestions_empty_when_no_clarification(self, mock_llm):
        """When needs_clarification=False, suggestions should be empty."""
        mock_llm.return_value = "MES 是製造執行系統。"

        result = loop.process_agent_turn("MES 是什麼")

        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["suggestions"], [])

    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    def test_suggestions_max_5(self, mock_llm):
        """Suggestions should not exceed 5 items."""
        # Use a question that matches many categories
        mock_llm.return_value = "請問您想查不良、良率、設備稼動還是在製品？"

        result = loop.process_agent_turn("不良良率設備在製？")

        self.assertTrue(result["needs_clarification"])
        self.assertLessEqual(len(result["suggestions"]), 5)


class TestFailedToolNotClarification(unittest.TestCase):
    @patch("mes_dashboard.services.ai_agent_loop.call_llm_text")
    @patch("mes_dashboard.services.ai_agent_loop.execute_tool")
    def test_failed_tool_not_treated_as_clarification(self, mock_execute, mock_llm):
        """If LLM called a tool but it failed, needs_clarification should be False
        even if the fallback answer contains a question mark."""
        mock_llm.side_effect = [
            '<tool_call>{"name": "reject_summary", "arguments": {"start_date": "2026-03-01", "end_date": "2026-03-18"}}</tool_call>',
            "查詢失敗，是否要換個方式查詢？",
        ]
        mock_execute.return_value = {
            "success": False,
            "result_summary": "",
            "chart_data": None,
            "error": "服務函式載入失敗",
        }

        result = loop.process_agent_turn("今天不良率？")

        # A tool was attempted → not a clarification
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(len(result["tool_trace"]), 1)


if __name__ == "__main__":
    unittest.main()
