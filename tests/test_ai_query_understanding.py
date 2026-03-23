# -*- coding: utf-8 -*-
"""Unit tests for AI slot-filling query understanding."""

import unittest

from mes_dashboard.services import ai_query_understanding as uds


class TestAdvanceQueryState(unittest.TestCase):
    def setUp(self):
        uds.reset_query_sessions_for_tests()

    def test_without_conversation_id_bypasses_session_state(self):
        result = uds.advance_query_state(
            conversation_id=None,
            user_input="查詢 WB 近 7 天不良趨勢",
            llm_caller=None,
        )

        self.assertTrue(result["ready_to_search"])
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["search_question"], "查詢 WB 近 7 天不良趨勢")

    def test_ambiguous_query_stores_session_and_returns_clarification(self):
        result = uds.advance_query_state(
            conversation_id="conv-1",
            user_input="WB 狀況",
            llm_caller=None,
        )

        self.assertFalse(result["ready_to_search"])
        self.assertTrue(result["needs_clarification"])
        self.assertGreater(len(result["missing_slots"]), 0)
        stored = uds.get_query_session_for_tests("conv-1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["initial_question"], "WB 狀況")

    def test_followup_fills_missing_slots_and_clears_session(self):
        first = uds.advance_query_state(
            conversation_id="conv-2",
            user_input="WB 狀況",
            llm_caller=None,
        )
        self.assertFalse(first["ready_to_search"])

        second = uds.advance_query_state(
            conversation_id="conv-2",
            user_input="看近 7 天不良趨勢",
            llm_caller=None,
        )

        self.assertTrue(second["ready_to_search"])
        self.assertFalse(second["needs_clarification"])
        self.assertIn("主題：不良 / Reject", second["search_question"])
        self.assertIn("範圍：焊接_WB", second["search_question"])
        self.assertIn("時間範圍：近 7 天", second["search_question"])
        self.assertIsNone(uds.get_query_session_for_tests("conv-2"))

    def test_llm_can_force_context_reset(self):
        uds.advance_query_state(
            conversation_id="conv-3",
            user_input="WB 狀況",
            llm_caller=None,
        )

        def fake_llm(_messages):
            return {
                "topic": "equipment",
                "intent": "status",
                "target_type": "equipment",
                "target_value": "GWBK-0247",
                "time_scope": "current",
                "metric": "設備狀態",
                "should_reset_context": True,
                "clarification_question": "",
                "suggestions": [],
            }

        result = uds.advance_query_state(
            conversation_id="conv-3",
            user_input="改看 GWBK-0247 現在狀態",
            llm_caller=fake_llm,
        )

        self.assertTrue(result["ready_to_search"])
        self.assertIn("GWBK-0247", result["search_question"])
        self.assertNotIn("焊接_WB", result["search_question"])
