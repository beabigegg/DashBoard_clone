# -*- coding: utf-8 -*-
"""Unit tests for ai_routes Blueprint.

Tests the thin HTTP layer: feature flag, input validation, service dispatch,
and error-to-HTTP-status mapping.  All service-layer calls are mocked.
"""

import json
import unittest
from unittest.mock import patch

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.core.rate_limit import reset_rate_limits_for_tests
from mes_dashboard.services.ai_query_understanding import reset_query_sessions_for_tests


class TestAiRoutesBase(unittest.TestCase):
    """Common setUp shared across AI route test classes."""

    def setUp(self):
        db._ENGINE = None
        self.app = create_app("testing")
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        reset_rate_limits_for_tests()
        reset_query_sessions_for_tests()


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------

class TestAiQueryFeatureFlag(TestAiRoutesBase):
    """Feature-flag gate: AI_QUERY_ENABLED controls access."""

    def test_ai_query_feature_flag_off_returns_404(self):
        """When _AI_QUERY_ENABLED is False the endpoint must return 404."""
        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", False):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢不良"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(payload["success"])


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestAiQueryInputValidation(TestAiRoutesBase):
    """Input validation: missing / blank question field."""

    def test_ai_query_missing_question_returns_400(self):
        """Empty JSON body (no 'question') must return 400 VALIDATION_ERROR."""
        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post("/api/ai/query", json={})
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")

    def test_ai_query_empty_question_returns_400(self):
        """Whitespace-only question must return 400 VALIDATION_ERROR."""
        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post("/api/ai/query", json={"question": "   "})
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestAiQuerySuccess(TestAiRoutesBase):
    """Happy-path: service returns a result dict."""

    _MOCK_RESULT = {
        "answer": "測試摘要回答",
        "chart_data": None,
        "query_used": "reject_spike_alerts",
        "params_used": {},
        "suggestions": [],
    }

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_ai_query_calls_service_and_returns_success(self, mock_process):
        """200 success response with data.answer matching service return value."""
        mock_process.return_value = self._MOCK_RESULT

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢不良"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["data"]["answer"], "測試摘要回答")
        mock_process.assert_called_once()

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_ai_query_passes_only_question(self, mock_process):
        """Route must pass question and conversation_id to service."""
        mock_process.return_value = self._MOCK_RESULT

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            self.client.post(
                "/api/ai/query",
                json={"question": "查詢不良", "conversation_id": "should-be-ignored"},
            )

        mock_process.assert_called_once_with(
            question="查詢不良",
            conversation_id="should-be-ignored",
        )

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_ai_query_returns_clarification_payload(self, mock_process):
        mock_process.return_value = {
            "answer": "請問您要看摘要還是趨勢？",
            "chart_data": None,
            "query_used": None,
            "params_used": None,
            "suggestions": ["摘要", "趨勢"],
            "needs_clarification": True,
            "missing_slots": ["intent"],
            "query_state": {"topic": "reject"},
        }

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "WB 不良", "conversation_id": "conv-clarify"},
            )

        payload = json.loads(response.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertTrue(payload["data"]["needs_clarification"])
        self.assertEqual(payload["data"]["missing_slots"], ["intent"])


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

class TestAiQueryErrorMapping(TestAiRoutesBase):
    """Service exceptions must map to the correct HTTP status and error code."""

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_ai_query_timeout_error_returns_504(self, mock_process):
        """TimeoutError from service → 504 EXTERNAL_SERVICE_TIMEOUT."""
        mock_process.side_effect = TimeoutError("逾時")

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢不良"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 504)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "EXTERNAL_SERVICE_TIMEOUT")

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_ai_query_connection_error_returns_502(self, mock_process):
        """ConnectionError from service → 502 EXTERNAL_SERVICE_ERROR."""
        mock_process.side_effect = ConnectionError("連線失敗")

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢不良"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 502)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "EXTERNAL_SERVICE_ERROR")

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_ai_query_validation_error_returns_400(self, mock_process):
        """ValueError from service → 400 VALIDATION_ERROR."""
        mock_process.side_effect = ValueError("param error")

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢不良"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")


class TestAiQueryEdgeCases(TestAiRoutesBase):
    """Edge cases: context-limit, tool-trace flag, clarification, conversation Redis round-trip."""

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_context_limit_returns_400(self, mock_process):
        """CONTEXT_LIMIT_REACHED exception from service must return 400."""
        mock_process.side_effect = ValueError("對話已達上限")

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "繼續上個問題"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_conversation_id_is_passed_to_service(self, mock_process):
        """conversation_id in request body must be forwarded to service layer."""
        mock_process.return_value = {"answer": "ok", "conversation_id": "conv-001"}

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢良率", "conversation_id": "conv-001"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        _, kwargs = mock_process.call_args
        self.assertEqual(kwargs.get("conversation_id"), "conv-001")

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_missing_conversation_id_defaults_to_none(self, mock_process):
        """Missing conversation_id must result in None being passed to service."""
        mock_process.return_value = {"answer": "ok", "conversation_id": "new-conv"}

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢良率"},
            )

        self.assertEqual(response.status_code, 200)
        _, kwargs = mock_process.call_args
        self.assertIsNone(kwargs.get("conversation_id"))

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_tool_trace_result_passes_through_envelope(self, mock_process):
        """Service result with tool_trace field must be returned in data envelope."""
        mock_process.return_value = {
            "answer": "良率為 95%",
            "tool_trace": [{"tool": "query_yield", "args": {}, "result": {}}],
            "conversation_id": "conv-abc",
        }

        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": "查詢良率"},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 200)
        self.assertIn("tool_trace", payload["data"])
        self.assertIsInstance(payload["data"]["tool_trace"], list)

    @patch("mes_dashboard.routes.ai_routes.ai_query_service.process_query")
    def test_empty_question_rejected(self, mock_process):
        """Empty question string must return 400 before service is called."""
        with patch("mes_dashboard.routes.ai_routes._AI_QUERY_ENABLED", True):
            response = self.client.post(
                "/api/ai/query",
                json={"question": ""},
            )
        payload = json.loads(response.data)

        self.assertEqual(response.status_code, 400)
        mock_process.assert_not_called()
        self.assertEqual(payload["error"]["code"], "VALIDATION_ERROR")
