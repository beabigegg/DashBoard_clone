# -*- coding: utf-8 -*-
"""Unit tests for ai_leader_orchestrator.py (AI_MODE=leader)."""
import unittest
from unittest.mock import patch

import requests

from mes_dashboard.services import ai_leader_orchestrator as leader


def _agent_result(answer="子任務回答", chart_data=None, tool_trace=None, query_used=None):
    return {
        "answer": answer,
        "chart_data": chart_data,
        "query_used": query_used,
        "params_used": None,
        "suggestions": [],
        "needs_clarification": False,
        "tool_trace": tool_trace if tool_trace is not None else [],
    }


class TestRespondPath(unittest.TestCase):
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_respond_action_returns_directly(self, mock_llm, mock_agent):
        """action=respond → answer returned as-is, no subagent dispatched."""
        mock_llm.return_value = {"action": "respond", "answer": "MES 是製造執行系統。"}

        result = leader.process_leader_turn("MES 是什麼？")

        self.assertEqual(result["answer"], "MES 是製造執行系統。")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["query_used"])
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["subtasks"], [])
        mock_agent.assert_not_called()

    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_respond_with_question_mark_is_clarification(self, mock_llm, mock_agent):
        """Respond answer containing '？' → needs_clarification with suggestions."""
        mock_llm.return_value = {"action": "respond", "answer": "請問您想查哪個站點的不良率？"}

        result = leader.process_leader_turn("不良率多少？")

        self.assertTrue(result["needs_clarification"])
        self.assertGreater(len(result["suggestions"]), 0)
        mock_agent.assert_not_called()

    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_respond_empty_answer_uses_fallback_text(self, mock_llm, mock_agent):
        """action=respond with empty answer → generic fallback message."""
        mock_llm.return_value = {"action": "respond", "answer": ""}

        result = leader.process_leader_turn("？？？")

        self.assertIn("換個方式", result["answer"])
        mock_agent.assert_not_called()


class TestDelegatePath(unittest.TestCase):
    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_two_tasks_dispatched_and_synthesized(self, mock_llm, mock_agent, mock_text):
        """Two subtasks each run through a subagent; leader synthesizes final answer."""
        mock_llm.return_value = {
            "action": "delegate",
            "tasks": ["查詢近 7 天焊接_DB 不良率趨勢", "查詢目前 Hold 批次摘要"],
        }
        mock_agent.side_effect = [
            _agent_result(
                answer="不良率 2.1%，趨勢平穩。",
                chart_data=[{"date": "2026-07-01", "reject_rate": 2.1}],
                tool_trace=[{"step": 1, "function": "reject_trend", "summary": "ok"}],
                query_used="reject_trend",
            ),
            _agent_result(
                answer="目前 Hold 12 批。",
                chart_data=[{"label": "Hold 批次", "value": 12}],
                tool_trace=[{"step": 1, "function": "wip_hold_summary", "summary": "ok"}],
                query_used="wip_hold_summary",
            ),
        ]
        mock_text.return_value = "近 7 天 DB 站不良率 2.1% 且平穩；目前 Hold 12 批。"

        result = leader.process_leader_turn("DB 站不良率趨勢和 Hold 狀況")

        self.assertEqual(result["answer"], "近 7 天 DB 站不良率 2.1% 且平穩；目前 Hold 12 批。")
        # query_used propagates the last chart-producing subagent's tool name
        # so AiChartRenderer picks the chart type by name suffix
        self.assertEqual(result["query_used"], "wip_hold_summary")
        # chart_data is the last non-null subagent chart
        self.assertEqual(result["chart_data"], [{"label": "Hold 批次", "value": 12}])
        self.assertEqual(mock_agent.call_count, 2)
        # Subagents receive the self-contained goal text
        self.assertEqual(mock_agent.call_args_list[0].args[0], "查詢近 7 天焊接_DB 不良率趨勢")
        # Two successful subtasks recorded
        self.assertEqual([st["success"] for st in result["subtasks"]], [True, True])
        # tool_trace: leader_plan + 2 namespaced subagent entries + leader_synthesize
        functions = [t["function"] for t in result["tool_trace"]]
        self.assertEqual(functions[0], "leader_plan")
        self.assertIn("subagent1.reject_trend", functions)
        self.assertIn("subagent2.wip_hold_summary", functions)
        self.assertEqual(functions[-1], "leader_synthesize")

    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_query_used_falls_back_to_leader_without_chart(self, mock_llm, mock_agent, mock_text):
        """No subagent produced a chart → query_used falls back to 'leader'."""
        mock_llm.return_value = {"action": "delegate", "tasks": ["查 A"]}
        mock_agent.return_value = _agent_result(answer="純文字結果", chart_data=None)
        mock_text.return_value = "答案"

        result = leader.process_leader_turn("查 A")

        self.assertEqual(result["query_used"], "leader")
        self.assertIsNone(result["chart_data"])

    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_synthesis_receives_question_and_subtask_results(self, mock_llm, mock_agent, mock_text):
        """Synthesis user message must contain the original question and each subtask answer."""
        mock_llm.return_value = {"action": "delegate", "tasks": ["查 A"]}
        mock_agent.return_value = _agent_result(answer="A 結果 42")
        mock_text.return_value = "答案"

        leader.process_leader_turn("原始問題 XYZ")

        synthesis_messages = mock_text.call_args.args[0]
        user_content = synthesis_messages[-1]["content"]
        self.assertIn("原始問題 XYZ", user_content)
        self.assertIn("A 結果 42", user_content)

    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_task_count_capped_at_max_tasks(self, mock_llm, mock_agent, mock_text):
        """More than MAX_TASKS planned tasks → only the first MAX_TASKS run."""
        mock_llm.return_value = {
            "action": "delegate",
            "tasks": [f"任務{i}" for i in range(1, 6)],
        }
        mock_agent.return_value = _agent_result()
        mock_text.return_value = "答案"

        result = leader.process_leader_turn("查很多東西")

        self.assertEqual(mock_agent.call_count, leader.MAX_TASKS)
        self.assertEqual(len(result["subtasks"]), leader.MAX_TASKS)

    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_delegate_with_empty_tasks_uses_question(self, mock_llm, mock_agent, mock_text):
        """action=delegate but empty tasks → whole question becomes the single subtask."""
        mock_llm.return_value = {"action": "delegate", "tasks": []}
        mock_agent.return_value = _agent_result()
        mock_text.return_value = "答案"

        leader.process_leader_turn("今天 WB 站不良率")

        mock_agent.assert_called_once()
        self.assertEqual(mock_agent.call_args.args[0], "今天 WB 站不良率")


class TestDegradation(unittest.TestCase):
    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_malformed_plan_degrades_to_single_task(self, mock_llm, mock_agent, mock_text):
        """Planning RuntimeError (unparseable JSON) → delegate whole question as one task."""
        mock_llm.side_effect = RuntimeError("Could not extract JSON")
        mock_agent.return_value = _agent_result(answer="查詢結果")
        mock_text.return_value = "最終回答"

        result = leader.process_leader_turn("今天不良率多少？")

        mock_agent.assert_called_once()
        self.assertEqual(mock_agent.call_args.args[0], "今天不良率多少？")
        self.assertEqual(result["answer"], "最終回答")

    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_planning_timeout_propagates(self, mock_llm):
        """requests.Timeout in planning → TimeoutError for the route layer."""
        mock_llm.side_effect = requests.Timeout("timeout")
        with self.assertRaises(TimeoutError):
            leader.process_leader_turn("查不良率")

    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_planning_connection_error_propagates(self, mock_llm):
        """requests.ConnectionError in planning → ConnectionError for the route layer."""
        mock_llm.side_effect = requests.ConnectionError("refused")
        with self.assertRaises(ConnectionError):
            leader.process_leader_turn("查不良率")

    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_one_failed_subagent_does_not_kill_turn(self, mock_llm, mock_agent, mock_text):
        """One subagent raising → its failure recorded, others still synthesized."""
        mock_llm.return_value = {"action": "delegate", "tasks": ["查 A", "查 B"]}
        mock_agent.side_effect = [RuntimeError("boom"), _agent_result(answer="B 結果")]
        mock_text.return_value = "部分結果回答"

        result = leader.process_leader_turn("A 和 B")

        self.assertEqual(result["answer"], "部分結果回答")
        self.assertEqual([st["success"] for st in result["subtasks"]], [False, True])
        self.assertIn("失敗", result["subtasks"][0]["answer"])

    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_all_subagents_failed_skips_synthesis(self, mock_llm, mock_agent, mock_text):
        """All subagents failed → failure report without a synthesis LLM call."""
        mock_llm.return_value = {"action": "delegate", "tasks": ["查 A", "查 B"]}
        mock_agent.side_effect = RuntimeError("boom")

        result = leader.process_leader_turn("A 和 B")

        self.assertIn("查詢執行失敗", result["answer"])
        mock_text.assert_not_called()

    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_synthesis_failure_falls_back_to_concatenation(self, mock_llm, mock_agent, mock_text):
        """Synthesis LLM failure → subagent answers concatenated, data never lost."""
        mock_llm.return_value = {"action": "delegate", "tasks": ["查 A"]}
        mock_agent.return_value = _agent_result(answer="A 結果 42")
        mock_text.side_effect = RuntimeError("LLM down")

        result = leader.process_leader_turn("查 A")

        self.assertIn("A 結果 42", result["answer"])


class TestChatHistory(unittest.TestCase):
    @patch("mes_dashboard.services.ai_leader_orchestrator.append_to_chat_history")
    @patch("mes_dashboard.services.ai_leader_orchestrator.get_chat_history")
    @patch("mes_dashboard.services.ai_leader_orchestrator.call_llm_text")
    @patch("mes_dashboard.services.ai_leader_orchestrator.process_agent_turn")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_history_injected_into_planning_and_appended(
        self, mock_llm, mock_agent, mock_text, mock_get_hist, mock_append
    ):
        """chat_history goes between system and user in planning; final answer appended."""
        mock_get_hist.return_value = [
            {"role": "user", "content": "先前問題"},
            {"role": "assistant", "content": "先前回答"},
        ]
        mock_llm.return_value = {"action": "delegate", "tasks": ["查 A"]}
        mock_agent.return_value = _agent_result()
        mock_text.return_value = "最終回答"

        leader.process_leader_turn("接續問題", conversation_id="conv-9")

        plan_messages = mock_llm.call_args.args[0]
        self.assertEqual(plan_messages[0]["role"], "system")
        self.assertEqual(plan_messages[1]["content"], "先前問題")
        self.assertEqual(plan_messages[-1]["content"], "接續問題")
        mock_append.assert_called_once_with("conv-9", "接續問題", "最終回答")

    @patch("mes_dashboard.services.ai_leader_orchestrator.append_to_chat_history")
    @patch("mes_dashboard.services.ai_leader_orchestrator._call_llm")
    def test_respond_path_does_not_append_history(self, mock_llm, mock_append):
        """Clarification/direct respond is not a final answer → no history append."""
        mock_llm.return_value = {"action": "respond", "answer": "請問要查哪個站別？"}

        leader.process_leader_turn("不良率？", conversation_id="conv-9")

        mock_append.assert_not_called()


class TestPromptContent(unittest.TestCase):
    def test_plan_prompt_mentions_capabilities_and_format(self):
        prompt = leader.build_leader_plan_prompt()
        for token in ["delegate", "respond", "tasks", "子任務", "SQL"]:
            self.assertIn(token, prompt)

    def test_synthesis_prompt_forbids_fabrication(self):
        prompt = leader.build_leader_synthesis_prompt()
        self.assertIn("不要編造", prompt)


if __name__ == "__main__":
    unittest.main()
