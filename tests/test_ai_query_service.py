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
    """Tests for call_llm_text()."""

    @patch("mes_dashboard.services.ai_query_service.requests.post")
    def test_returns_content_text(self, mock_post):
        """call_llm_text must return raw text without JSON parsing."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "這是自然語言回答"}}]
        }
        mock_post.return_value = mock_response

        result = svc.call_llm_text([{"role": "user", "content": "test"}])
        self.assertEqual(result, "這是自然語言回答")

    @patch("mes_dashboard.services.ai_query_service.requests.post")
    def test_fallback_to_reasoning_content(self, mock_post):
        """call_llm_text must fall back to reasoning_content if content is empty."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "", "reasoning_content": "推理文字"}}]
        }
        mock_post.return_value = mock_response

        result = svc.call_llm_text([{"role": "user", "content": "test"}])
        self.assertEqual(result, "推理文字")


class TestSummarizeForLlm(unittest.TestCase):
    """Tests for summarize_for_llm()."""

    def test_pareto_full(self):
        """Pareto data under max_chars must be returned in full."""
        data = {"categories": ["A", "B"], "values": [10, 5]}
        result = svc.summarize_for_llm("reject_reason_pareto", data)
        self.assertIn("A", result)
        self.assertIn("10", result)

    def test_trend_truncation(self):
        """Trend data with > 30 points must be truncated to head/tail + stats."""
        items = [{"date": f"2026-01-{i:02d}", "reject_rate": float(i)} for i in range(1, 35)]
        result = svc.summarize_for_llm("reject_trend", items)
        self.assertIn("前5筆", result)
        self.assertIn("後5筆", result)
        self.assertIn("統計", result)

    def test_trend_no_truncation_under_30(self):
        """Trend data with <= 30 points must be returned as-is."""
        items = [{"date": f"2026-01-{i:02d}", "reject_rate": 1.0} for i in range(1, 10)]
        result = svc.summarize_for_llm("reject_trend", items)
        self.assertNotIn("前5筆", result)

    def test_heatmap_top10(self):
        """Heatmap must include top-10 cells."""
        data = {
            "xAxis": ["A", "B"],
            "yAxis": ["X", "Y"],
            "data": [[0, 0, 100], [0, 1, 50], [1, 0, 200]],
        }
        result = svc.summarize_for_llm("wip_matrix", data)
        self.assertIn("top10_cells", result)

    def test_table_truncation(self):
        """Table data with > 10 rows must include first 10 + total count."""
        rows = [{"id": i, "val": i * 2} for i in range(20)]
        result = svc.summarize_for_llm("reject_lot_list", rows)
        self.assertIn("共", result)
        self.assertIn("20", result)

    def test_kpi_full(self):
        """KPI data must be returned in full."""
        data = [{"label": "總批次", "value": 100}]
        result = svc.summarize_for_llm("wip_summary", data)
        self.assertIn("總批次", result)

    def test_none_returns_placeholder(self):
        """None chart_data must return a placeholder string."""
        result = svc.summarize_for_llm("reject_reason_pareto", None)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_fallback_unknown_chart_type(self):
        """Unknown chart type must fall back to json.dumps truncation."""
        data = {"foo": "bar"}
        result = svc.summarize_for_llm("unknown_fn", data)
        self.assertIn("bar", result)


class TestProcessQueryLLMErrors(unittest.TestCase):
    """Tests for LLM connectivity error propagation in process_query()."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_llm_timeout_raises_timeout(self, mock_call_llm):
        """requests.Timeout from Round 1 _call_llm must surface as TimeoutError."""
        mock_call_llm.side_effect = requests.Timeout("timed out")

        with self.assertRaises(TimeoutError):
            svc.process_query_function("question")

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_llm_connection_error_raises_connection_error(self, mock_call_llm):
        """requests.ConnectionError from Round 1 _call_llm must surface as ConnectionError."""
        mock_call_llm.side_effect = requests.ConnectionError("connection refused")

        with self.assertRaises(ConnectionError):
            svc.process_query_function("question")


class TestProcessQueryNullIntent(unittest.TestCase):
    """Tests for process_query() when LLM returns null function intent."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_null_intent_returns_answer(self, mock_call_llm):
        """When Round 1 returns function=None, result must have answer set and no chart_data."""
        mock_call_llm.return_value = {
            "function": None,
            "explanation": "無法理解",
        }

        result = svc.process_query_function("gibberish")

        self.assertEqual(result["answer"], "無法理解")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["query_used"])
        self.assertNotIn("conversation_id", result)


class TestProcessQueryValidIntent(unittest.TestCase):
    """Tests for process_query() happy path with a valid LLM intent."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_valid_intent_dispatches_service(
        self,
        mock_call_llm,
        mock_get_svc,
        mockcall_llm_text,
    ):
        """Valid combined-call pipeline must dispatch service and return query_used + answer."""
        # Combined call: returns function + params in one result
        mock_call_llm.return_value = {
            "function": "reject_spike_alerts",
            "params": {"detector": "reject"},
            "explanation": "查詢不良突增",
        }
        mock_service_fn = MagicMock(return_value={"items": [{"detector": "reject", "severity": "warning"}]})
        mock_get_svc.return_value = mock_service_fn
        mockcall_llm_text.return_value = "近期發現 1 筆不良突增異常。"

        result = svc.process_query_function("查詢最近不良突增")

        self.assertEqual(result["query_used"], "reject_spike_alerts")
        self.assertEqual(result["answer"], "近期發現 1 筆不良突增異常。")
        self.assertNotIn("conversation_id", result)
        self.assertNotIn("round", result)
        mock_service_fn.assert_called_once_with(detector="reject")

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_process_query_no_conversation_id_in_response(
        self, mock_call_llm, mock_get_svc, mockcall_llm_text
    ):
        """Response must not contain conversation_id, round, or max_rounds."""
        mock_call_llm.return_value = {
            "function": "reject_spike_alerts",
            "params": {"detector": "reject"},
            "explanation": "查詢",
        }
        mock_get_svc.return_value = MagicMock(return_value={"items": []})
        mockcall_llm_text.return_value = "無異常。"

        result = svc.process_query_function("查詢")

        self.assertNotIn("conversation_id", result)
        self.assertNotIn("round", result)
        self.assertNotIn("max_rounds", result)


class TestRound3Fallback(unittest.TestCase):
    """Round 3 failure must not propagate — chart_data still returned."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_round3_failure_returns_fallback_answer(
        self, mock_call_llm, mock_get_svc, mockcall_llm_text
    ):
        """When Round 3 raises, answer must be the fallback text and chart_data intact."""
        mock_call_llm.return_value = {
            "function": "reject_spike_alerts",
            "params": {"detector": "reject"},
            "explanation": "查詢",
        }
        mock_service_fn = MagicMock(return_value={"items": [{"id": 1}]})
        mock_get_svc.return_value = mock_service_fn
        mockcall_llm_text.side_effect = RuntimeError("LLM R3 failed")

        result = svc.process_query_function("查詢")

        self.assertEqual(result["answer"], "查詢完成，請參考圖表。")
        self.assertIsNotNone(result["chart_data"])
        self.assertEqual(result["query_used"], "reject_spike_alerts")


# ---------------------------------------------------------------------------
# Text-to-SQL pipeline tests
# ---------------------------------------------------------------------------

class TestText2SqlHappyPath(unittest.TestCase):
    """process_query_text2sql() happy path: LLM generates SQL, DB returns rows."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_happy_path_returns_all_fields(self, mock_call_llm, mockcall_llm_text):
        import pandas as pd
        mock_call_llm.side_effect = [
            {"domains": ["hold"], "thought": "需要查詢 Hold 資料"},
            {
                "sql": "SELECT CONTAINERID, HOLDTXNDATE FROM DWH.DW_MES_HOLDRELEASEHISTORY FETCH FIRST 10 ROWS ONLY",
                "params": {"start_date": "2026-03-11", "end_date": "2026-03-18"},
                "explanation": "查詢近期 Hold 紀錄",
            },
            {"approved": True},  # Reviewer
        ]
        mockcall_llm_text.return_value = "近期 Hold 共 3 筆，主要原因為外觀不良。"

        df = pd.DataFrame([
            {"CONTAINERID": "AAAA0001", "HOLDTXNDATE": "2026-03-15"},
            {"CONTAINERID": "AAAA0002", "HOLDTXNDATE": "2026-03-16"},
        ])

        with patch("mes_dashboard.core.database.read_sql_df", return_value=df):
            result = svc.process_query_text2sql("近 7 天 Hold 了哪些批次？")

        self.assertEqual(result["query_used"], "text2sql")
        self.assertIn("answer", result)
        self.assertIn("chart_data", result)
        self.assertIn("sql_used", result)
        self.assertIn("tool_trace", result)
        self.assertIn("params_used", result)
        self.assertIn("suggestions", result)
        self.assertIsNotNone(result["sql_used"])
        self.assertIsInstance(result["tool_trace"], list)
        self.assertIsInstance(result["chart_data"], list)
        self.assertEqual(len(result["chart_data"]), 2)

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_happy_path_tool_trace_contains_stages(self, mock_call_llm, mockcall_llm_text):
        import pandas as pd
        mock_call_llm.side_effect = [
            {"domains": ["wip_realtime"], "thought": "查詢即時在製"},
            {"sql": "SELECT CONTAINERID FROM DWH.DW_MES_LOT_V FETCH FIRST 5 ROWS ONLY",
             "params": {}, "explanation": "即時在製查詢"},
            {"approved": True},  # Reviewer
        ]
        mockcall_llm_text.return_value = "目前在製 5 筆。"
        df = pd.DataFrame([{"CONTAINERID": f"ID{i}"} for i in range(5)])

        with patch("mes_dashboard.core.database.read_sql_df", return_value=df):
            result = svc.process_query_text2sql("目前在製有多少批？")

        steps = [t["function"] for t in result["tool_trace"]]
        self.assertIn("stage1_classify", steps)
        self.assertIn("stage2_generate_sql", steps)
        self.assertIn("execute_sql", steps)
        self.assertIn("stage3_summarize", steps)


class TestText2SqlSqlErrorRetrySuccess(unittest.TestCase):
    """First SQL fails, LLM corrects, second attempt succeeds."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_retry_success(self, mock_call_llm, mockcall_llm_text):
        import pandas as pd
        mock_call_llm.side_effect = [
            {"domains": ["reject"], "thought": "查詢不良"},
            # First SQL attempt
            {"sql": "SELECT BAD_COL FROM DWH.DW_MES_LOTREJECTHISTORY FETCH FIRST 10 ROWS ONLY",
             "params": {}, "explanation": "不良查詢"},
            {"approved": True},  # Reviewer (passes, but SQL will fail at Oracle)
            # Second SQL attempt (corrected by LLM after Oracle error)
            {"sql": "SELECT CONTAINERID FROM DWH.DW_MES_LOTREJECTHISTORY FETCH FIRST 10 ROWS ONLY",
             "params": {}, "explanation": "修正後查詢"},
            {"approved": True},  # Reviewer
        ]
        mockcall_llm_text.return_value = "查詢到 2 筆不良紀錄。"
        df = pd.DataFrame([{"CONTAINERID": "X001"}, {"CONTAINERID": "X002"}])

        call_count = {"n": 0}
        def mock_read_sql(sql, params):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("ORA-00904: \"BAD_COL\": invalid identifier")
            return df

        with patch("mes_dashboard.core.database.read_sql_df", side_effect=mock_read_sql):
            result = svc.process_query_text2sql("查詢不良紀錄")

        self.assertEqual(result["query_used"], "text2sql")
        self.assertIsNotNone(result["chart_data"])
        self.assertIsNotNone(result["sql_used"])
        # trace should include both attempts
        error_steps = [t for t in result["tool_trace"] if t.get("error")]
        self.assertEqual(len(error_steps), 1)


class TestText2SqlAllRetriesFail(unittest.TestCase):
    """All 3 SQL execution attempts fail → return error message."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_all_retries_return_error(self, mock_call_llm):
        mock_call_llm.side_effect = [
            {"domains": ["hold"], "thought": "查詢"},
            {"sql": "SELECT X FROM DWH.DW_MES_HOLDRELEASEHISTORY FETCH FIRST 10 ROWS ONLY",
             "params": {}, "explanation": "查詢"},
            {"approved": True},  # Reviewer
            {"sql": "SELECT Y FROM DWH.DW_MES_HOLDRELEASEHISTORY FETCH FIRST 10 ROWS ONLY",
             "params": {}, "explanation": "再次查詢"},
            {"approved": True},  # Reviewer
            {"sql": "SELECT Z FROM DWH.DW_MES_HOLDRELEASEHISTORY FETCH FIRST 10 ROWS ONLY",
             "params": {}, "explanation": "第三次查詢"},
            {"approved": True},  # Reviewer
        ]

        with patch("mes_dashboard.core.database.read_sql_df",
                   side_effect=Exception("ORA-00904: invalid identifier")):
            result = svc.process_query_text2sql("Hold 查詢")

        self.assertEqual(result["query_used"], "text2sql")
        self.assertIsNone(result["chart_data"])
        self.assertIn("失敗", result["answer"])
        self.assertIsNotNone(result["sql_used"])


class TestText2SqlEmptyResult(unittest.TestCase):
    """SQL succeeds but returns 0 rows → no Stage 3 call."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_empty_result_no_stage3(self, mock_call_llm, mockcall_llm_text):
        import pandas as pd
        mock_call_llm.side_effect = [
            {"domains": ["material"], "thought": "查詢材料"},
            {"sql": "SELECT CONTAINERID FROM DWH.DW_MES_LOTMATERIALSHISTORY FETCH FIRST 10 ROWS ONLY",
             "params": {}, "explanation": "材料查詢"},
            {"approved": True},  # Reviewer
        ]
        empty_df = pd.DataFrame()

        with patch("mes_dashboard.core.database.read_sql_df", return_value=empty_df):
            result = svc.process_query_text2sql("這個材料批號用過嗎？")

        # Stage 3 should NOT be called
        mockcall_llm_text.assert_not_called()
        self.assertIsNone(result["chart_data"])
        self.assertIn("無符合", result["answer"])


class TestText2SqlNoDomains(unittest.TestCase):
    """Stage 1 returns empty domains → return thought as answer."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_no_domains_returns_thought(self, mock_call_llm):
        mock_call_llm.return_value = {
            "domains": [],
            "thought": "這個問題無法對應 MES 資料領域",
        }

        result = svc.process_query_text2sql("今天天氣如何？")

        self.assertEqual(result["query_used"], "text2sql")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["sql_used"])
        self.assertIn("無法", result["answer"])
        # Stage 2 must not be called (only 1 LLM call: Stage 1)
        self.assertEqual(mock_call_llm.call_count, 1)


class TestFeatureFlag(unittest.TestCase):
    """AI_MODE feature flag controls which pipeline is used."""

    @patch("mes_dashboard.services.ai_query_service.process_query_function")
    def test_function_mode_routes_to_function_pipeline(self, mock_fn):
        mock_fn.return_value = {"answer": "ok", "query_used": "test_fn"}
        with patch.dict("os.environ", {"AI_MODE": "function"}):
            result = svc.process_query("test question")
        mock_fn.assert_called_once()
        # The first positional arg must be the search question
        called_question = mock_fn.call_args.args[0] if mock_fn.call_args.args else mock_fn.call_args.kwargs.get("question")
        self.assertEqual(called_question, "test question")

    @patch("mes_dashboard.services.ai_query_service.process_query_text2sql")
    def test_text2sql_mode_routes_to_text2sql_pipeline(self, mock_t2s):
        mock_t2s.return_value = {"answer": "ok", "query_used": "text2sql"}
        with patch.dict("os.environ", {"AI_MODE": "text2sql"}):
            result = svc.process_query("test question")
        mock_t2s.assert_called_once()
        called_question = mock_t2s.call_args.args[0] if mock_t2s.call_args.args else mock_t2s.call_args.kwargs.get("question")
        self.assertEqual(called_question, "test question")

    @patch("mes_dashboard.services.ai_query_service.process_query_text2sql")
    def test_default_mode_is_text2sql(self, mock_t2s):
        mock_t2s.return_value = {"answer": "ok", "query_used": "text2sql"}
        env_without_ai_mode = {k: v for k, v in __import__("os").environ.items() if k != "AI_MODE"}
        with patch.dict("os.environ", env_without_ai_mode, clear=True):
            result = svc.process_query("test question")
        mock_t2s.assert_called_once()
        called_question = mock_t2s.call_args.args[0] if mock_t2s.call_args.args else mock_t2s.call_args.kwargs.get("question")
        self.assertEqual(called_question, "test question")


class TestStructuredClarificationFlow(unittest.TestCase):
    @patch("mes_dashboard.services.ai_query_service.process_query_text2sql")
    @patch("mes_dashboard.services.ai_query_service.advance_query_state")
    def test_process_query_returns_clarification_before_search(self, mock_advance, mock_t2s):
        mock_advance.return_value = {
            "ready_to_search": False,
            "needs_clarification": True,
            "answer": "請問您要看摘要還是趨勢？",
            "suggestions": ["摘要", "趨勢"],
            "missing_slots": ["intent"],
            "query_state": {"topic": "reject"},
        }

        result = svc.process_query("WB 不良", conversation_id="conv-1")

        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["missing_slots"], ["intent"])
        self.assertEqual(result["query_state"], {"topic": "reject"})
        mock_t2s.assert_not_called()

    @patch("mes_dashboard.services.ai_query_service.process_query_text2sql")
    @patch("mes_dashboard.services.ai_query_service.advance_query_state")
    def test_process_query_uses_enriched_search_question(self, mock_advance, mock_t2s):
        mock_advance.return_value = {
            "ready_to_search": True,
            "needs_clarification": False,
            "search_question": "原始問題：WB 不良\n已確認查詢條件：\n- 主題：不良 / Reject",
            "query_state": {"topic": "reject", "intent": "summary"},
        }
        mock_t2s.return_value = {"answer": "ok", "query_used": "text2sql"}

        result = svc.process_query("WB 不良", conversation_id="conv-2")

        mock_t2s.assert_called_once()
        called_question = mock_t2s.call_args.args[0]
        self.assertIn("主題：不良 / Reject", called_question)
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["query_state"], {"topic": "reject", "intent": "summary"})


class TestText2SqlTimeoutError(unittest.TestCase):
    """SQL execution timeout → return error immediately, no retry."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_timeout_no_retry(self, mock_call_llm):
        from mes_dashboard.core.database import DatabasePoolExhaustedError

        mock_call_llm.side_effect = [
            {"domains": ["hold"], "thought": "查詢"},
            {"sql": "SELECT CONTAINERID FROM DWH.DW_MES_HOLDRELEASEHISTORY FETCH FIRST 10 ROWS ONLY",
             "params": {}, "explanation": "查詢"},
            {"approved": True},  # Reviewer
        ]

        with patch("mes_dashboard.core.database.read_sql_df",
                   side_effect=DatabasePoolExhaustedError("pool exhausted", retry_after_seconds=5)):
            result = svc.process_query_text2sql("Hold 查詢")

        self.assertEqual(result["query_used"], "text2sql")
        self.assertIsNone(result["chart_data"])
        self.assertIn("連線異常", result["answer"])
        # LLM should only be called 3 times (Stage 1 + Stage 2 + Reviewer), no retry
        self.assertEqual(mock_call_llm.call_count, 3)


class TestExtractOracleError(unittest.TestCase):
    """_extract_oracle_error helper extracts ORA-xxxxx codes."""

    def test_extracts_ora_code(self):
        exc = Exception("cx_Oracle.DatabaseError: ORA-00904: \"BAD_COL\": invalid identifier")
        result = svc._extract_oracle_error(exc)
        self.assertIn("ORA-00904", result)

    def test_returns_full_message_if_no_ora(self):
        exc = Exception("some other error")
        result = svc._extract_oracle_error(exc)
        self.assertEqual(result, "some other error")


class TestSummarizeDataframe(unittest.TestCase):
    """_summarize_dataframe truncates large DataFrames."""

    def test_empty_df_returns_empty_message(self):
        import pandas as pd
        result = svc._summarize_dataframe(pd.DataFrame())
        self.assertIn("空", result)

    def test_large_df_truncated_to_10_rows(self):
        import pandas as pd
        df = pd.DataFrame({"col": range(100)})
        result = svc._summarize_dataframe(df)
        self.assertIn("100", result)  # shows total count
        self.assertIn("10", result)   # shows 10 rows

    def test_small_df_not_truncated(self):
        import pandas as pd
        df = pd.DataFrame({"col": [1, 2, 3]})
        result = svc._summarize_dataframe(df)
        self.assertIn("1", result)
        self.assertIn("3", result)


class TestSanitizeSql(unittest.TestCase):
    """_sanitize_sql deterministic SQL fixes."""

    def test_auto_quotes_package(self):
        sql = "SELECT e.Package FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V e"
        result = svc._sanitize_sql(sql)
        self.assertIn('"Package"', result)
        self.assertNotIn("e.Package", result)

    def test_auto_quotes_function(self):
        sql = 'SELECT e.Function FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V e'
        result = svc._sanitize_sql(sql)
        self.assertIn('"Function"', result)

    def test_does_not_double_quote(self):
        sql = 'SELECT e."Package" FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V e'
        result = svc._sanitize_sql(sql)
        # Should not produce e.""Package""
        self.assertEqual(result.count('"Package"'), 1)

    def test_leaves_normal_columns_alone(self):
        sql = "SELECT e.EQUIPMENTID, e.SPEC FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V e"
        result = svc._sanitize_sql(sql)
        self.assertEqual(result, sql)

    def test_package_in_where_clause(self):
        sql = "SELECT * FROM DWH.DW_MES_EQUIPMENTSTATUS_WIP_V e WHERE e.Package = :pkg"
        result = svc._sanitize_sql(sql)
        self.assertIn('e."Package"', result)


class TestCoerceDateParams(unittest.TestCase):
    """_coerce_date_params handles various LLM date formats."""

    def test_sysdate(self):
        from datetime import datetime
        result = svc._coerce_date_params({"end_date": "SYSDATE"})
        self.assertIsInstance(result["end_date"], datetime)

    def test_sysdate_minus_n(self):
        from datetime import datetime
        result = svc._coerce_date_params({"start_date": "SYSDATE-7"})
        self.assertIsInstance(result["start_date"], datetime)

    def test_iso_date_string(self):
        from datetime import datetime
        result = svc._coerce_date_params({"d": "2026-03-11"})
        self.assertEqual(result["d"], datetime(2026, 3, 11))

    def test_non_date_untouched(self):
        result = svc._coerce_date_params({"pattern": "%S1%", "count": 5})
        self.assertEqual(result["pattern"], "%S1%")
        self.assertEqual(result["count"], 5)


class TestDeterministicSqlReviewer(unittest.TestCase):
    """Deterministic reviewer catches business-critical SQL misses."""

    def test_rejects_station_rate_sql_without_group_aggregation(self):
        question = "昨天有哪些站點良率較低？"
        sql = (
            "SELECT r.WORKCENTERNAME, SUM(r.REJECTQTY) AS TOTAL_REJECT, "
            "SUM(r.MOVEINQTY) AS TOTAL_IN "
            "FROM DWH.DW_MES_LOTREJECTHISTORY r "
            "WHERE r.TXNDATE >= :start_date AND r.TXNDATE < :end_date "
            "GROUP BY r.WORKCENTERNAME "
            "ORDER BY TOTAL_REJECT DESC FETCH FIRST 20 ROWS ONLY"
        )
        issues = svc._deterministic_review_issues(question, sql, ["yield"])
        self.assertTrue(any("WORKCENTER_GROUP" in msg for msg in issues))

    def test_rejects_rate_sql_without_reject_exclusion_policy(self):
        question = "近 7 天不良率最高的站別？"
        sql = (
            "SELECT r.WORKCENTER_GROUP, SUM(r.REJECTQTY) AS TOTAL_REJECT, "
            "SUM(r.MOVEINQTY) AS TOTAL_IN "
            "FROM DWH.DW_MES_LOTREJECTHISTORY r "
            "WHERE r.TXNDATE >= :start_date AND r.TXNDATE < :end_date "
            "GROUP BY r.WORKCENTER_GROUP "
            "ORDER BY TOTAL_REJECT DESC FETCH FIRST 20 ROWS ONLY"
        )
        issues = svc._deterministic_review_issues(question, sql, ["reject"])
        self.assertTrue(any("Reject 排除規則" in msg for msg in issues))


# ---------------------------------------------------------------------------
# IP-2: Combined call tests (AC-1, AC-7)
# ---------------------------------------------------------------------------

class TestCombinedCallOneCallOnly(unittest.TestCase):
    """AC-1: process_query_function must issue exactly ONE _call_llm call for select+fill."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_only_one_llm_call_for_select_and_fill(
        self, mock_call_llm, mock_get_svc, mock_llm_text
    ):
        """Combined call must issue exactly one _call_llm call (not two)."""
        mock_call_llm.return_value = {
            "function": "reject_spike_alerts",
            "params": {"detector": "reject"},
            "explanation": "查詢不良突增",
        }
        mock_get_svc.return_value = MagicMock(
            return_value={"items": [{"detector": "reject"}]}
        )
        mock_llm_text.return_value = "發現 1 筆不良突增。"

        svc.process_query_function("查詢最近不良突增")

        # Must be called exactly once (combined select+fill), not twice
        self.assertEqual(mock_call_llm.call_count, 1)


class TestCombinedCallOutputSchema(unittest.TestCase):
    """AC-1: combined call output must contain function, params, explanation keys."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_combined_call_result_uses_function_and_params_keys(
        self, mock_call_llm, mock_get_svc, mock_llm_text
    ):
        """process_query_function must extract function+params from combined result dict."""
        mock_call_llm.return_value = {
            "function": "reject_spike_alerts",
            "params": {"detector": "reject"},
            "explanation": "查詢不良突增",
        }
        mock_get_svc.return_value = MagicMock(
            return_value={"items": [{"severity": "warning"}]}
        )
        mock_llm_text.return_value = "近期發現 1 筆不良突增異常。"

        result = svc.process_query_function("查詢最近不良突增")
        self.assertEqual(result["query_used"], "reject_spike_alerts")
        # params must have been forwarded to service
        call_args = mock_get_svc.return_value.call_args
        self.assertIsNotNone(call_args)


class TestCombinedCallNullIntent(unittest.TestCase):
    """AC-1: combined call with function=null must return null-intent path without raising."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_null_function_returns_explanation_as_answer(self, mock_call_llm):
        mock_call_llm.return_value = {
            "function": None,
            "params": {},
            "explanation": "無法理解查詢",
        }
        result = svc.process_query_function("gibberish")
        self.assertEqual(result["answer"], "無法理解查詢")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["query_used"])

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_missing_function_key_returns_fallback(self, mock_call_llm):
        """Combined result without 'function' key must also fall through to null-intent."""
        mock_call_llm.return_value = {
            "explanation": "無對應函式",
        }
        result = svc.process_query_function("something")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["query_used"])


class TestCombinedCallMalformedJson(unittest.TestCase):
    """AC-7: malformed combined call response must return null-intent path, not raise."""

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_call_llm_raises_runtime_error_returns_null_intent(self, mock_call_llm):
        """RuntimeError from _call_llm in combined call must not propagate."""
        mock_call_llm.side_effect = RuntimeError("Cannot extract JSON from LLM response")
        # Must NOT raise — must return a graceful null-intent result
        result = svc.process_query_function("any query")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["query_used"])

    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_empty_dict_from_call_llm_returns_null_intent(self, mock_call_llm):
        """Empty dict (no function key) from _call_llm must map to null-intent path."""
        mock_call_llm.return_value = {}
        result = svc.process_query_function("any query")
        self.assertIsNone(result["chart_data"])
        self.assertIsNone(result["query_used"])


class TestCombinedCallPartialJson(unittest.TestCase):
    """AC-7: partial JSON (no params key) must not raise; service called with empty params."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_missing_params_key_defaults_to_empty_dict(
        self, mock_call_llm, mock_get_svc, mock_llm_text
    ):
        """Combined result with function but no params key must use {} as params."""
        mock_call_llm.return_value = {
            "function": "dashboard_kpi",
            "explanation": "查看 KPI",
            # No "params" key
        }
        mock_get_svc.return_value = MagicMock(return_value={"total": 10})
        mock_llm_text.return_value = "全廠設備 KPI 摘要。"

        result = svc.process_query_function("查看全廠 KPI")
        # Should succeed (dashboard_kpi has no required params)
        self.assertEqual(result["query_used"], "dashboard_kpi")


class TestHistoryInjectedIntoCombinedCall(unittest.TestCase):
    """AC-3: chat_history must be injected between system and user turn in combined call."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_history_injected_in_messages(
        self, mock_call_llm, mock_get_svc, mock_llm_text
    ):
        """When conversation_id has prior history, it must appear in combined call messages."""
        from mes_dashboard.services.ai_query_understanding import (
            append_to_chat_history,
            reset_query_sessions_for_tests,
        )
        reset_query_sessions_for_tests()

        # Pre-seed history
        append_to_chat_history("conv-hist", "上一個問題", "上一個答案")

        mock_call_llm.return_value = {
            "function": "dashboard_kpi",
            "params": {},
            "explanation": "KPI",
        }
        mock_get_svc.return_value = MagicMock(return_value={"total": 5})
        mock_llm_text.return_value = "KPI 摘要。"

        svc.process_query_function("查看 KPI", conversation_id="conv-hist")

        # Inspect messages passed to _call_llm
        call_args = mock_call_llm.call_args
        messages = call_args.args[0] if call_args.args else call_args.kwargs.get("messages", [])
        roles = [m["role"] for m in messages]
        contents = [m["content"] for m in messages]

        # system must come first, history in the middle, user last
        self.assertEqual(roles[0], "system")
        self.assertEqual(roles[-1], "user")
        self.assertIn("上一個問題", contents)
        self.assertIn("上一個答案", contents)


class TestProductionHistoryQueryDispatchAdapter(unittest.TestCase):
    """AC-6: production_history_query must receive params as a single positional dict."""

    @patch("mes_dashboard.services.ai_query_service.call_llm_text")
    @patch("mes_dashboard.services.ai_query_service.get_service_function")
    @patch("mes_dashboard.services.ai_query_service._call_llm")
    def test_raw_params_dispatch_passes_dict_not_kwargs(
        self, mock_call_llm, mock_get_svc, mock_llm_text
    ):
        """production_history_query must call service_fn(params_dict), not service_fn(**params)."""
        mock_call_llm.return_value = {
            "function": "production_history_query",
            "params": {"start_date": "2026-01-01", "end_date": "2026-01-07"},
            "explanation": "查詢生產歷程",
        }
        mock_service_fn = MagicMock(return_value={"rows": []})
        mock_get_svc.return_value = mock_service_fn
        mock_llm_text.return_value = "查詢完成。"

        svc.process_query_function("查詢生產歷程")

        # Must be called with ONE positional dict argument (raw_params), not **kwargs
        call_args = mock_service_fn.call_args
        # Positional args (not keyword)
        pos_args = call_args.args
        kw_args = call_args.kwargs
        # Either called as fn(params_dict) with one positional arg
        # or the dict is passed as-is — ensure start_date is IN a dict, not as kwarg
        if pos_args:
            self.assertIsInstance(pos_args[0], dict)
            self.assertIn("start_date", pos_args[0])
        else:
            # If kwargs, we should fail — dispatch adapter requires positional dict
            self.fail("production_history_query must be called with a single positional dict, not kwargs")


class TestNormalizeChartDataNewFunctions(unittest.TestCase):
    """AC-6: normalize_chart_data for the three new functions returns expected shapes."""

    def test_qc_gate_status_extracts_stations(self):
        raw = {"cache_time": "2026-01-01", "stations": [{"name": "DB", "count": 3}]}
        result = svc.normalize_chart_data("qc_gate_status", raw)
        self.assertEqual(result, [{"name": "DB", "count": 3}])

    def test_qc_gate_status_non_dict_raw_passthrough(self):
        raw = [{"name": "DB", "count": 3}]
        result = svc.normalize_chart_data("qc_gate_status", raw)
        self.assertEqual(result, raw)

    def test_qc_gate_status_empty_dict_returns_empty_list(self):
        raw = {}
        result = svc.normalize_chart_data("qc_gate_status", raw)
        self.assertEqual(result, [])

    def test_production_history_query_passthrough(self):
        raw = {"rows": [{"lot": "GA001"}], "total": 1}
        result = svc.normalize_chart_data("production_history_query", raw)
        self.assertEqual(result, raw)

    def test_resource_history_summary_passthrough(self):
        raw = {"kpi": {"ou_pct": 85.0}, "trend": []}
        result = svc.normalize_chart_data("resource_history_summary", raw)
        self.assertEqual(result, raw)
