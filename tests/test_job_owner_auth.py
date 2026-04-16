# -*- coding: utf-8 -*-
"""Regression tests for job ownership authorisation.

Key test: round-trip through enqueue_job() asserts that meta["owner"] is
written to Redis — this is the test that would have caught the original bug
where enqueue_job() never wrote owner and abandon was unauthenticated.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

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
# Helper: build a job_meta dict that get_job_status returns
# ---------------------------------------------------------------------------

def _make_meta(status="queued", owner="alice"):
    return {"job_id": "job-001", "status": status, "owner": owner}


# ---------------------------------------------------------------------------
# Round-trip: enqueue_job writes owner to Redis
# (This is the canonical regression test for the original bug)
# ---------------------------------------------------------------------------

class TestEnqueueJobWritesOwnerToRedis:
    """enqueue_job() must persist owner into Redis meta on enqueue."""

    def test_owner_written_to_redis_on_enqueue(self):
        """owner kwarg must appear in the HSET mapping written to Redis."""
        import mes_dashboard.services.async_query_job_service as svc

        mock_conn = MagicMock()
        mock_queue = MagicMock()

        svc._RQ_AVAILABLE = None
        with patch.object(svc, "_check_rq_installed", return_value=True), \
             patch.object(svc, "get_control_redis_client", return_value=mock_conn), \
             patch.object(svc, "get_redis_client", return_value=mock_conn), \
             patch("rq.Queue", return_value=mock_queue):
            job_id, err = svc.enqueue_job(
                queue_name="reject-query",
                worker_fn=lambda **kw: None,
                owner="alice",
                prefix="reject",
            )

        assert job_id is not None
        assert err is None

        # Verify the initial HSET call includes owner=alice
        initial_hset = mock_conn.hset.call_args_list[0]
        mapping = initial_hset.kwargs.get("mapping") or initial_hset[1].get("mapping")
        assert mapping.get("owner") == "alice", (
            "enqueue_job() did not write owner into Redis meta — this is the original bug"
        )

    def test_enqueue_job_without_owner_raises_type_error(self):
        """Omitting owner kwarg must raise TypeError immediately (contract enforcement)."""
        import mes_dashboard.services.async_query_job_service as svc

        with pytest.raises(TypeError, match="owner"):
            svc.enqueue_job(
                queue_name="reject-query",
                worker_fn=lambda **kw: None,
                # owner intentionally omitted
            )


# ---------------------------------------------------------------------------
# abandon_job: session-based owner check
# ---------------------------------------------------------------------------

class TestAbandonOwnerSessionCheck:
    """abandon_job must derive owner from session, not from request body."""

    def test_same_logged_in_session_can_abandon_own_job(self, client):
        """Logged-in user abandons a job they own → 200."""
        job_meta = _make_meta(status="queued", owner="alice")
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}

        with (
            patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta),
            patch("mes_dashboard.routes.job_routes.update_job_progress"),
        ):
            rv = client.post("/api/job/job-001/abandon", json={"prefix": "reject"})

        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        assert body["data"]["status"] == "abandoned"

    def test_different_logged_in_user_cannot_abandon(self, client):
        """Different logged-in user attempting to abandon → 403."""
        job_meta = _make_meta(status="queued", owner="alice")
        with client.session_transaction() as sess:
            sess["user"] = {"username": "bob", "is_admin": False}

        with patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta):
            rv = client.post("/api/job/job-001/abandon", json={"prefix": "reject"})

        assert rv.status_code == 403
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "FORBIDDEN"

    def test_anonymous_session_can_abandon_own_job(self, client):
        """Anonymous session that originally enqueued can abandon via matching cookie token."""
        anon_token = "abcdef1234567890abcdef1234567890"
        job_meta = _make_meta(status="queued", owner=anon_token)
        with client.session_transaction() as sess:
            sess["mes_owner_token"] = anon_token

        with (
            patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta),
            patch("mes_dashboard.routes.job_routes.update_job_progress"),
        ):
            rv = client.post("/api/job/job-001/abandon", json={"prefix": "reject"})

        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True

    def test_different_anonymous_session_cannot_abandon(self, client):
        """A different anonymous cookie must not be able to abandon another session's job."""
        original_token = "aaaa1111aaaa1111aaaa1111aaaa1111"
        attacker_token = "bbbb2222bbbb2222bbbb2222bbbb2222"
        job_meta = _make_meta(status="queued", owner=original_token)
        with client.session_transaction() as sess:
            sess["mes_owner_token"] = attacker_token

        with patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta):
            rv = client.post("/api/job/job-001/abandon", json={"prefix": "reject"})

        assert rv.status_code == 403
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "FORBIDDEN"

    def test_body_owner_field_is_ignored(self, client):
        """Supplying a matching owner in the request body must NOT bypass the session check."""
        job_meta = _make_meta(status="queued", owner="alice")
        with client.session_transaction() as sess:
            sess["user"] = {"username": "bob", "is_admin": False}

        with patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta):
            # body contains alice's owner value but session is bob → must be 403
            rv = client.post(
                "/api/job/job-001/abandon",
                json={"prefix": "reject", "owner": "alice"},
            )

        assert rv.status_code == 403
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "FORBIDDEN"

    def test_legacy_meta_without_owner_is_fail_closed(self, client):
        """A job whose meta has no owner field must return 403 (fail-closed)."""
        job_meta = {"job_id": "job-legacy", "status": "queued"}  # no owner key
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}

        with patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta):
            rv = client.post("/api/job/job-legacy/abandon", json={"prefix": "reject"})

        assert rv.status_code == 403
        body = rv.get_json()
        assert body["success"] is False
        assert body["error"]["code"] == "FORBIDDEN"

    def test_meta_owner_none_is_fail_closed(self, client):
        """meta owner=None (from get_job_status returning None for missing key) → 403."""
        job_meta = {"job_id": "job-002", "status": "queued", "owner": None}
        with client.session_transaction() as sess:
            sess["user"] = {"username": "alice", "is_admin": False}

        with patch("mes_dashboard.routes.job_routes.get_job_status", return_value=job_meta):
            rv = client.post("/api/job/job-002/abandon", json={"prefix": "reject"})

        assert rv.status_code == 403
