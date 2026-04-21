# -*- coding: utf-8 -*-
"""Tests for the three-layer gate on `GET /internal/metrics`.

Maps 1:1 to openspec harden-real-infra-test-coverage 3.3 (six tests) and
covers the spec scenarios in the
`/internal/metrics` Internal-only requirement:
  * Production config does not register the blueprint
  * Testing config registers but runtime env gate blocks
  * All gates open for loopback callers
  * Non-loopback request is rejected even when other gates are open

The URL-map / `sys.modules` assertions (tests #1 and #6) run in a
subprocess.  Purging ``sys.modules['mes_dashboard.*']`` from the main
pytest process would re-identify every class the rest of the suite has
already imported and cause cascading teardown failures across unrelated
tests — subprocess isolation keeps the assertion honest without
contaminating sibling tests.  Tests #2–#5 reuse a single in-process
TestingConfig client since they only flip env vars + request headers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest


_EXPECTED_KEYS = frozenset({
    "pool",
    "duckdb",
    "redis",
    "spool",
    "worker_rss",
    "circuit_breaker",
    "rq",
})

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_in_subprocess(script: str, env: Dict[str, str] | None = None) -> Dict[str, Any]:
    """Run `script` in a fresh Python interpreter and return parsed JSON stdout.

    The subprocess ends its stdout with a JSON object on the final line;
    anything before it is test-side logging that we discard.
    """
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    # Testing config needs this for downstream code paths (csrf etc.).
    full_env.setdefault("PORTAL_SPA_ENABLED", "true")
    # Prevent .env pollution so the subprocess starts with a clean
    # Layer 2 gate state.
    full_env.pop("INTERNAL_METRICS_ENABLED", None)

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO_ROOT),
        env=full_env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        pytest.fail(
            f"subprocess exited {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    # Last non-empty line is the JSON payload.
    payload_line = ""
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line:
            payload_line = line
            break
    try:
        return json.loads(payload_line)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"subprocess did not emit JSON on final line: {exc}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# In-process client for env/loopback gate tests (2-5)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def testing_client():
    """Build one testing-config app and hand out its test client.

    These four tests only flip env vars and request headers, so reusing a
    single app instance is safe and keeps the suite fast.  Engine singleton
    is nulled out so the testing config's DB settings take effect.
    """
    from mes_dashboard.app import create_app
    import mes_dashboard.core.database as _db
    _db._ENGINE = None
    app = create_app("testing")
    yield app.test_client()


# ---------------------------------------------------------------------------
# Test 1 — REGISTER_INTERNAL_METRICS=False → no URL rule for /internal/metrics
# ---------------------------------------------------------------------------

def test_flag_false_omits_internal_metrics_from_url_map():
    """Layer 1 (URL-map side): any config with ``REGISTER_INTERNAL_METRICS``
    False MUST omit the rule from ``app.url_map``.

    Subprocess-isolated so the flag toggle + fresh module import cannot
    affect the rest of the pytest collection.
    """
    script = r"""
import json, sys, os
sys.path.insert(0, 'src')
from mes_dashboard.config import settings
settings.TestingConfig.REGISTER_INTERNAL_METRICS = False
import mes_dashboard.core.database as _db
_db._ENGINE = None
from mes_dashboard.app import create_app
app = create_app('testing')
has_rule = any(r.rule == '/internal/metrics' for r in app.url_map.iter_rules())
print(json.dumps({'has_rule': has_rule}))
"""
    result = _run_in_subprocess(script)
    assert result["has_rule"] is False, (
        "With REGISTER_INTERNAL_METRICS=False the URL map must not contain "
        "/internal/metrics."
    )


# ---------------------------------------------------------------------------
# Test 2 — Layer 2 blocks when INTERNAL_METRICS_ENABLED is unset
# ---------------------------------------------------------------------------

def test_env_gate_blocks_when_env_var_unset(testing_client, monkeypatch):
    """Layer 2: blueprint registered, INTERNAL_METRICS_ENABLED unset → 404."""
    monkeypatch.delenv("INTERNAL_METRICS_ENABLED", raising=False)
    resp = testing_client.get("/internal/metrics")
    assert resp.status_code == 404
    body: Dict[str, Any] = resp.get_json() or {}
    assert body.get("success") is False
    assert body.get("error", {}).get("code") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Test 3 — Layer 2 blocks when env is "0"
# ---------------------------------------------------------------------------

def test_env_gate_blocks_when_env_var_is_zero(testing_client, monkeypatch):
    """Layer 2: env set to '0' is still off; only the literal '1' opens."""
    monkeypatch.setenv("INTERNAL_METRICS_ENABLED", "0")
    resp = testing_client.get("/internal/metrics")
    assert resp.status_code == 404
    body: Dict[str, Any] = resp.get_json() or {}
    assert body.get("error", {}).get("code") == "NOT_FOUND"


# ---------------------------------------------------------------------------
# Test 4 — Layer 3 blocks non-loopback remote_addr even with env=1
# ---------------------------------------------------------------------------

def test_loopback_gate_blocks_non_loopback_remote_addr(testing_client, monkeypatch):
    """Layer 3: env gate open but remote_addr is non-loopback → still 404.

    The response MUST NOT leak any metrics data even though the registered
    route is present; this is the defense-in-depth guarantee.
    """
    monkeypatch.setenv("INTERNAL_METRICS_ENABLED", "1")
    resp = testing_client.get(
        "/internal/metrics",
        environ_overrides={"REMOTE_ADDR": "10.0.0.5"},
    )
    assert resp.status_code == 404
    body: Dict[str, Any] = resp.get_json() or {}
    assert body.get("error", {}).get("code") == "NOT_FOUND"
    # Paranoid: the rejection envelope has no "data" object that could
    # accidentally ship metrics.  'data' must not appear at top level.
    assert "data" not in body


# ---------------------------------------------------------------------------
# Test 5 — All gates open → 200 + 7-key snapshot
# ---------------------------------------------------------------------------

def test_all_gates_open_returns_seven_category_snapshot(testing_client, monkeypatch):
    """Layer 1 + 2 + 3 all open → 200 with the stable seven-key contract.

    This is the canary for the metrics shape the soak probe depends on —
    if any key disappears, the soak assertions can't target that category.
    """
    monkeypatch.setenv("INTERNAL_METRICS_ENABLED", "1")
    # Flask test_client defaults REMOTE_ADDR to 127.0.0.1, which satisfies
    # Layer 3 without further overrides.
    resp = testing_client.get("/internal/metrics")
    assert resp.status_code == 200, resp.data
    body: Dict[str, Any] = resp.get_json() or {}
    assert body.get("success") is True
    data = body.get("data") or {}
    assert set(data.keys()) == _EXPECTED_KEYS, (
        f"expected exactly {_EXPECTED_KEYS}, got {set(data.keys())}"
    )
    # rq section must itself be a dict mapping queue name to the five
    # registry counters (scenario "All gates open for loopback callers").
    rq_section = data.get("rq") or {}
    if rq_section.get("enabled"):
        by_queue = rq_section.get("by_queue") or {}
        assert isinstance(by_queue, dict)
        for qname, counts in by_queue.items():
            assert isinstance(qname, str)
            for key in ("pending", "started", "failed", "finished", "deferred"):
                assert key in counts, f"queue {qname} missing {key}"


# ---------------------------------------------------------------------------
# Test 6 — production config factory does not import internal_routes module
# ---------------------------------------------------------------------------

def test_production_factory_does_not_import_internal_routes_module():
    """Layer 1 (sys.modules side): the real production factory must not
    import ``internal_routes`` at all — no URL rule, no module reference.

    Subprocess-isolated because the sys.modules assertion must observe a
    cold interpreter — if another test in the suite has already imported
    internal_routes under the testing factory, the assertion would be
    meaningless in-process.
    """
    script = r"""
import json, sys, os
sys.path.insert(0, 'src')
import mes_dashboard.core.database as _db
_db._ENGINE = None
from mes_dashboard.app import create_app
app = create_app('production')
has_rule = any(r.rule == '/internal/metrics' for r in app.url_map.iter_rules())
mod_imported = 'mes_dashboard.routes.internal_routes' in sys.modules
print(json.dumps({'has_rule': has_rule, 'mod_imported': mod_imported}))
"""
    result = _run_in_subprocess(
        script,
        env={
            "SECRET_KEY": "production-test-only-secret",
            "FLASK_ENV": "production",
        },
    )
    assert result["has_rule"] is False, (
        "Production config should not register /internal/metrics in URL map."
    )
    assert result["mod_imported"] is False, (
        "Production factory must not import mes_dashboard.routes.internal_routes."
    )
