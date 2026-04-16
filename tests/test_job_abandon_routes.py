# -*- coding: utf-8 -*-
"""Route tests for POST /api/job/<id>/abandon."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mes_dashboard.app import create_app


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestAbandonValidation:
    """Missing or invalid input must produce 400."""

    def test_missing_prefix_returns_400(self, client):
        rv = client.post("/api/job/job-abc123/abandon", json={})
        assert rv.status_code == 400
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "VALIDATION_ERROR"

    def test_empty_prefix_returns_400(self, client):
        rv = client.post("/api/job/job-abc123/abandon", json={"prefix": ""})
        assert rv.status_code == 400
        body = rv.get_json()
        assert body["success"] is False

    def test_no_body_returns_400(self, client):
        rv = client.post("/api/job/job-abc123/abandon")
        assert rv.status_code == 400
        body = rv.get_json()
        assert body["success"] is False


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------

class TestAbandonNotFound:
    """Unknown job_id or prefix returns 404."""

    def test_unknown_job_returns_404(self, client):
        with patch(
            "mes_dashboard.routes.job_routes.get_job_status",
            return_value=None,
        ):
            rv = client.post(
                "/api/job/nonexistent-001/abandon",
                json={"prefix": "reject"},
            )

        assert rv.status_code == 404
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Owner check
# ---------------------------------------------------------------------------

class TestAbandonOwnerCheck:
    """Owner is derived from the Flask session, never from the request body."""

    def test_matching_session_owner_succeeds(self, client, app):
        """Session username matches job owner → 200."""
        job_meta = {"job_id": "job-001", "status": "queued", "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with (
            patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta),
            patch("mes_dashboard.routes.job_routes.update_job_progress"),
        ):
            rv = client.post(
                "/api/job/job-001/abandon",
                json={"prefix": "reject"},
            )

        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        assert body["data"]["status"] == "abandoned"

    def test_wrong_session_owner_returns_403(self, client, app):
        """Different session username → 403."""
        job_meta = {"job_id": "job-002", "status": "queued", "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "bob", "is_admin": False}
        with patch(
            "mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta
        ):
            rv = client.post(
                "/api/job/job-002/abandon",
                json={"prefix": "reject"},
            )

        assert rv.status_code == 403
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "FORBIDDEN"

    def test_no_owner_in_job_meta_is_fail_closed(self, client, app):
        """Job without owner field → 403 (fail-closed; legacy job)."""
        job_meta = {"job_id": "job-004", "status": "queued"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with patch(
            "mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta
        ):
            rv = client.post(
                "/api/job/job-004/abandon",
                json={"prefix": "yield_alert"},
            )

        assert rv.status_code == 403
        body = rv.get_json()
        assert body["success"] is False


# ---------------------------------------------------------------------------
# Abandon active jobs
# ---------------------------------------------------------------------------

class TestAbandonActiveJob:
    """Active jobs (queued/running/started) can be abandoned."""

    @pytest.mark.parametrize("status", ["queued", "running", "started"])
    def test_active_status_abandoned_successfully(self, client, app, status):
        job_meta = {"job_id": "job-010", "status": status, "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with (
            patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta),
            patch("mes_dashboard.routes.job_routes.update_job_progress") as mock_update,
        ):
            rv = client.post(
                "/api/job/job-010/abandon",
                json={"prefix": "reject"},
            )

        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        assert body["data"]["job_id"] == "job-010"
        assert body["data"]["status"] == "abandoned"
        assert body["data"]["already_abandoned"] is False
        mock_update.assert_called_once_with("reject", "job-010", status="abandoned")

    def test_response_envelope_has_meta_timestamp(self, client, app):
        job_meta = {"job_id": "job-011", "status": "queued", "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with (
            patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta),
            patch("mes_dashboard.routes.job_routes.update_job_progress"),
        ):
            rv = client.post(
                "/api/job/job-011/abandon",
                json={"prefix": "reject"},
            )

        body = rv.get_json()
        assert "meta" in body
        assert "timestamp" in body["meta"]


# ---------------------------------------------------------------------------
# Idempotent re-abandon
# ---------------------------------------------------------------------------

class TestAbandonIdempotent:
    """Abandoning an already-abandoned job is idempotent (200 with flag)."""

    def test_already_abandoned_returns_200_with_flag(self, client, app):
        job_meta = {"job_id": "job-020", "status": "abandoned", "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with patch(
            "mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta
        ):
            rv = client.post(
                "/api/job/job-020/abandon",
                json={"prefix": "reject"},
            )

        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        assert body["data"]["already_abandoned"] is True
        assert body["data"]["status"] == "abandoned"

    def test_double_abandon_does_not_call_update(self, client, app):
        """update_job_progress must NOT be called when already abandoned."""
        job_meta = {"job_id": "job-021", "status": "abandoned", "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with (
            patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta),
            patch("mes_dashboard.routes.job_routes.update_job_progress") as mock_update,
        ):
            client.post("/api/job/job-021/abandon", json={"prefix": "reject"})
            mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# Terminal non-abandonable states
# ---------------------------------------------------------------------------

class TestAbandonTerminalConflict:
    """Completed/failed jobs cannot be abandoned (409 conflict)."""

    @pytest.mark.parametrize("status", ["completed", "failed"])
    def test_terminal_status_returns_409(self, client, app, status):
        job_meta = {"job_id": "job-030", "status": status, "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with patch(
            "mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta
        ):
            rv = client.post(
                "/api/job/job-030/abandon",
                json={"prefix": "reject"},
            )

        assert rv.status_code == 409
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "JOB_ALREADY_TERMINAL"

    def test_409_body_mentions_current_status(self, client, app):
        job_meta = {"job_id": "job-031", "status": "completed", "owner": "alice"}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}
        with patch(
            "mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta
        ):
            rv = client.post(
                "/api/job/job-031/abandon",
                json={"prefix": "production-history"},
            )

        body = rv.get_json()
        assert "completed" in body["error"]["message"]
