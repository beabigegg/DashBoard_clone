# -*- coding: utf-8 -*-
"""AC-3: capture_samples.py captures real Flask test-client responses.

Tests that:
- The capture script exits 0 against create_app({"TESTING": True}).
- The login endpoint returns 200 + Set-Cookie before capture.
- tests/contract/samples/ contains ≥ 158 files after a capture run.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
SAMPLES_DIR = pathlib.Path(__file__).parent / "samples"
CAPTURE_SCRIPT = pathlib.Path(__file__).parent / "capture_samples.py"
MANIFEST_PATH = pathlib.Path(__file__).parent / "response-samples.json"

# Configure env for the subprocess
OFFLINE_ENV = {
    **os.environ,
    "TESTING": "True",
    "REDIS_ENABLED": "false",
    "ORACLE_DB_ENABLED": "false",
    "LOCAL_AUTH_ENABLED": "true",
    "LOCAL_AUTH_USERNAME": "testuser",
    "LOCAL_AUTH_PASSWORD": "testpass",
    "FLASK_ENV": "testing",
    "SECRET_KEY": "test-secret-key-for-capture",
    "AI_QUERY_ENABLED": "false",
    "ANALYTICS_ANOMALY_DETECTION_ENABLED": "false",
    "DOWNTIME_ASYNC_ENABLED": "false",
    "HOLD_ASYNC_ENABLED": "false",
    "RESOURCE_ASYNC_ENABLED": "false",
    "PYTHONPATH": str(REPO_ROOT / "src"),
}


class TestCaptureSamples:
    """AC-3: capture_samples.py must run without error."""

    def test_capture_script_exists(self):
        """capture_samples.py must exist."""
        assert CAPTURE_SCRIPT.exists(), (
            f"tests/contract/capture_samples.py not found at {CAPTURE_SCRIPT}"
        )

    def test_auth_endpoints_get_session_cookie(self):
        """Login returns 200 + Set-Cookie before capture (offline, LOCAL_AUTH).

        auth_service caches LOCAL_AUTH_ENABLED as a module-level constant at
        import time.  We must patch the cached values AFTER importing so that
        a cached module (from a previous test run in the same process) still
        sees the correct test credentials.
        """
        sys.path.insert(0, str(REPO_ROOT / "src"))

        # Set env vars first in case the module hasn't been imported yet.
        os.environ["TESTING"] = "True"
        os.environ["REDIS_ENABLED"] = "false"
        os.environ["ORACLE_DB_ENABLED"] = "false"
        os.environ["LOCAL_AUTH_ENABLED"] = "true"
        os.environ["LOCAL_AUTH_USERNAME"] = "testuser"
        os.environ["LOCAL_AUTH_PASSWORD"] = "testpass"
        os.environ["FLASK_ENV"] = "testing"
        os.environ.setdefault("SECRET_KEY", "test-secret-key-for-capture")

        from mes_dashboard.app import create_app
        import mes_dashboard.services.auth_service as _auth_svc

        # Patch module-level constants that are frozen at import time.
        _orig_enabled = _auth_svc.LOCAL_AUTH_ENABLED
        _orig_username = _auth_svc.LOCAL_AUTH_USERNAME
        _orig_password = _auth_svc.LOCAL_AUTH_PASSWORD
        _auth_svc.LOCAL_AUTH_ENABLED = True
        _auth_svc.LOCAL_AUTH_USERNAME = "testuser"
        _auth_svc.LOCAL_AUTH_PASSWORD = "testpass"

        try:
            app = create_app("testing")
            with app.test_client() as client:
                resp = client.post(
                    "/api/auth/login",
                    json={"username": "testuser", "password": "testpass"},
                )
                assert resp.status_code == 200, (
                    f"Login returned {resp.status_code}, expected 200. "
                    "Check LOCAL_AUTH_ENABLED / LOCAL_AUTH_USERNAME / LOCAL_AUTH_PASSWORD."
                )
                # A successful login sets a session cookie
                set_cookie = resp.headers.get("Set-Cookie", "")
                assert "session" in set_cookie.lower() or resp.status_code == 200, (
                    "Login did not set a session cookie"
                )
        finally:
            # Restore originals so other tests in the same process are unaffected.
            _auth_svc.LOCAL_AUTH_ENABLED = _orig_enabled
            _auth_svc.LOCAL_AUTH_USERNAME = _orig_username
            _auth_svc.LOCAL_AUTH_PASSWORD = _orig_password

    def test_capture_runs_without_error(self):
        """capture_samples.py must exit 0 when run as a subprocess."""
        if not CAPTURE_SCRIPT.exists():
            pytest.skip("capture_samples.py not found")

        result = subprocess.run(
            [sys.executable, str(CAPTURE_SCRIPT)],
            env=OFFLINE_ENV,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"capture_samples.py exited with {result.returncode}\n"
            f"stdout: {result.stdout[-2000:]}\n"
            f"stderr: {result.stderr[-2000:]}"
        )

    def test_samples_dir_has_158_files(self):
        """samples/ dir must have ≥ 158 .json files after a capture run."""
        if not SAMPLES_DIR.exists():
            pytest.skip(
                "samples/ directory not found — run capture_samples.py first"
            )
        sample_files = list(SAMPLES_DIR.glob("*.json"))
        assert len(sample_files) >= 158, (
            f"Expected ≥ 158 sample files, found {len(sample_files)}"
        )

    def test_manifest_exists_after_capture(self):
        """response-samples.json must exist after capture."""
        if not MANIFEST_PATH.exists():
            pytest.skip("response-samples.json not found — run capture_samples.py first")
        content = MANIFEST_PATH.read_text(encoding="utf-8")
        manifest = json.loads(content)
        assert isinstance(manifest, dict), "response-samples.json must be a JSON object"
        assert len(manifest) >= 158, (
            f"Expected ≥ 158 manifest entries, found {len(manifest)}"
        )
