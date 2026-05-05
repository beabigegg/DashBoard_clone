# -*- coding: utf-8 -*-
"""Unit tests for the map_service_errors route decorator."""


from mes_dashboard.core.exceptions import (
    UserInputError,
    ResourceNotFoundError,
    QueryTimeoutError,
    DataContractError,
    InternalQueryError,
)
from mes_dashboard.core.response import (
    VALIDATION_ERROR,
    NOT_FOUND,
    QUERY_TIMEOUT,
    INTERNAL_ERROR,
)
from mes_dashboard.routes.query_tool_routes import map_service_errors


def _make_handler(exc):
    """Return a dummy route handler that raises *exc*."""
    @map_service_errors
    def handler():
        raise exc
    return handler


class TestMapServiceErrors:
    """Each exception class must produce the right HTTP status + error code."""

    def test_user_input_error_gives_400(self, app):
        with app.test_request_context():
            resp, status = _make_handler(UserInputError("bad input"))()
        assert status == 400
        assert resp.get_json()["error"]["code"] == VALIDATION_ERROR

    def test_user_input_error_message_preserved(self, app):
        with app.test_request_context():
            resp, status = _make_handler(UserInputError("請選擇設備"))()
        assert resp.get_json()["error"]["message"] == "請選擇設備"

    def test_resource_not_found_gives_404(self, app):
        with app.test_request_context():
            resp, status = _make_handler(ResourceNotFoundError("找不到 LOT"))()
        assert status == 404
        assert resp.get_json()["error"]["code"] == NOT_FOUND

    def test_query_timeout_gives_504(self, app):
        with app.test_request_context():
            resp, status = _make_handler(QueryTimeoutError("查詢逾時"))()
        assert status == 504
        assert resp.get_json()["error"]["code"] == QUERY_TIMEOUT

    def test_data_contract_error_gives_500(self, app):
        with app.test_request_context():
            resp, status = _make_handler(
                DataContractError("缺少欄位", details={"column": "EQUIPMENTID"})
            )()
        assert status == 500
        assert resp.get_json()["error"]["code"] == INTERNAL_ERROR

    def test_internal_query_error_gives_500(self, app):
        with app.test_request_context():
            resp, status = _make_handler(
                InternalQueryError("查詢失敗", cause=ValueError("db gone"))
            )()
        assert status == 500
        assert resp.get_json()["error"]["code"] == INTERNAL_ERROR

    def test_bare_exception_gives_500(self, app):
        with app.test_request_context():
            resp, status = _make_handler(RuntimeError("unexpected"))()
        assert status == 500
        assert resp.get_json()["error"]["code"] == INTERNAL_ERROR

    def test_success_passthrough(self, app):
        """When no exception is raised, the handler's return value is unchanged."""
        from mes_dashboard.core.response import success_response

        @map_service_errors
        def handler():
            return success_response({"ok": True})

        with app.test_request_context():
            resp, status = handler()
        assert status == 200
        assert resp.get_json()["data"] == {"ok": True}

    def test_data_contract_error_logs(self, app):
        """DataContractError must be handled without re-raising."""
        exc = DataContractError("schema drift", details={"column": "X"})
        with app.test_request_context():
            resp, status = _make_handler(exc)()
        # If the decorator logged and returned properly, status is 500
        assert status == 500

    def test_internal_query_error_logs(self, app):
        """InternalQueryError must be handled without re-raising."""
        cause = ValueError("root cause")
        exc = InternalQueryError("query failed", cause=cause)
        with app.test_request_context():
            resp, status = _make_handler(exc)()
        assert status == 500
