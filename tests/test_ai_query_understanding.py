# -*- coding: utf-8 -*-
"""Unit tests for AI slot-filling query understanding."""

import unittest

from mes_dashboard.services import ai_query_understanding as uds


class TestChatHistoryAppendOnSuccess(unittest.TestCase):
    """AC-4: append_to_chat_history appends user/assistant pair on success."""

    def setUp(self):
        uds.reset_query_sessions_for_tests()

    def test_append_creates_pair(self):
        uds.append_to_chat_history("conv-a", "問題1", "答案1")
        history = uds.get_chat_history("conv-a")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], {"role": "user", "content": "問題1"})
        self.assertEqual(history[1], {"role": "assistant", "content": "答案1"})

    def test_append_multiple_pairs_ordered(self):
        uds.append_to_chat_history("conv-b", "q1", "a1")
        uds.append_to_chat_history("conv-b", "q2", "a2")
        history = uds.get_chat_history("conv-b")
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["content"], "q1")
        self.assertEqual(history[2]["content"], "q2")

    def test_get_history_missing_key_returns_empty(self):
        history = uds.get_chat_history("nonexistent-conv")
        self.assertEqual(history, [])


class TestChatHistoryNoAppendOnFailure(unittest.TestCase):
    """AC-4: get_history returns copy; mutation must not affect stored state."""

    def setUp(self):
        uds.reset_query_sessions_for_tests()

    def test_get_history_returns_copy_not_reference(self):
        """Returned list must be a copy; mutation must not affect stored state."""
        uds.append_to_chat_history("conv-c", "q", "a")
        h1 = uds.get_chat_history("conv-c")
        h1.append({"role": "user", "content": "injected"})
        h2 = uds.get_chat_history("conv-c")
        self.assertEqual(len(h2), 2)  # original unchanged


class TestChatHistoryAppendOnEmptyResult(unittest.TestCase):
    """AC-4: empty-result answers DO get appended (they are contextually useful)."""

    def setUp(self):
        uds.reset_query_sessions_for_tests()

    def test_empty_result_answer_is_stored(self):
        empty_answer = "查詢完成，但沒有回傳任何資料。"
        uds.append_to_chat_history("conv-e", "有資料嗎？", empty_answer)
        history = uds.get_chat_history("conv-e")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[1]["content"], empty_answer)


class TestChatHistoryCapEnforcement(unittest.TestCase):
    """AC-5: cap at 8 pairs (16 messages), FIFO eviction."""

    def setUp(self):
        uds.reset_query_sessions_for_tests()

    def test_nine_pairs_evicts_oldest(self):
        for i in range(9):
            uds.append_to_chat_history("conv-cap", f"q{i}", f"a{i}")
        history = uds.get_chat_history("conv-cap")
        # Must have at most 16 messages (8 pairs)
        self.assertLessEqual(len(history), 16)
        # Oldest pair (q0/a0) must be gone
        contents = [m["content"] for m in history]
        self.assertNotIn("q0", contents)
        self.assertNotIn("a0", contents)

    def test_oldest_evicted_first(self):
        for i in range(10):
            uds.append_to_chat_history("conv-fifo", f"question{i}", f"answer{i}")
        history = uds.get_chat_history("conv-fifo")
        contents = [m["content"] for m in history]
        # Newest pair must be present
        self.assertIn("question9", contents)
        self.assertIn("answer9", contents)


class TestChatHistoryCapExactBoundary(unittest.TestCase):
    """AC-5: exactly 8 pairs fills to cap without eviction."""

    def setUp(self):
        uds.reset_query_sessions_for_tests()

    def test_exactly_eight_pairs_no_eviction(self):
        for i in range(8):
            uds.append_to_chat_history("conv-exact", f"q{i}", f"a{i}")
        history = uds.get_chat_history("conv-exact")
        self.assertEqual(len(history), 16)
        # All pairs present
        for i in range(8):
            contents = [m["content"] for m in history]
            self.assertIn(f"q{i}", contents)

    def test_ninth_pair_evicts_first(self):
        for i in range(9):
            uds.append_to_chat_history("conv-ninth", f"q{i}", f"a{i}")
        history = uds.get_chat_history("conv-ninth")
        self.assertEqual(len(history), 16)
        contents = [m["content"] for m in history]
        self.assertNotIn("q0", contents)
        self.assertIn("q8", contents)


class TestHistorySurvivesAdvanceQueryStatePop(unittest.TestCase):
    """AC-3 / R3: chat_history must survive the ready_to_search pop."""

    def setUp(self):
        uds.reset_query_sessions_for_tests()

    def test_history_survives_slot_filling_completion(self):
        """After advance_query_state reaches ready_to_search, history must persist."""
        # Pre-seed chat history for this conversation
        uds.append_to_chat_history("conv-r3", "先前問題", "先前答案")

        # Simulate a complete-slot turn that reaches ready_to_search
        # Provide a full question that rule-based extractor can resolve without LLM
        result = uds.advance_query_state(
            conversation_id="conv-r3",
            user_input="查詢 WB 近 7 天不良趨勢",
            llm_caller=None,
        )
        self.assertTrue(result["ready_to_search"])

        # History must still be accessible
        history = uds.get_chat_history("conv-r3")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["content"], "先前問題")
        self.assertEqual(history[1]["content"], "先前答案")


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
