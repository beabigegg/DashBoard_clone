# -*- coding: utf-8 -*-
"""Pytest configuration and fixtures for MES Dashboard tests."""

import pytest
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_TMP_DIR = os.path.join(_PROJECT_ROOT, 'tmp')

# Test baseline env: keep pytest isolated from local runtime/.env side effects.
os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('REDIS_ENABLED', 'false')
os.environ.setdefault('RUNTIME_CONTRACT_ENFORCE', 'false')
os.environ.setdefault('SLOW_QUERY_THRESHOLD', '1.0')
os.environ.setdefault('WATCHDOG_RUNTIME_DIR', _TMP_DIR)
os.environ.setdefault('WATCHDOG_RESTART_FLAG', os.path.join(_TMP_DIR, 'mes_dashboard_restart.flag'))
os.environ.setdefault('WATCHDOG_PID_FILE', os.path.join(_TMP_DIR, 'gunicorn.pid'))
os.environ.setdefault('WATCHDOG_STATE_FILE', os.path.join(_TMP_DIR, 'mes_dashboard_restart_state.json'))

import mes_dashboard.core.database as db
from mes_dashboard.app import create_app
from mes_dashboard.core.modernization_policy import clear_modernization_policy_cache


@pytest.fixture
def app():
    """Create application for testing."""
    db._ENGINE = None
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture(autouse=True)
def _reset_modernization_policy_cache():
    """Keep policy-cache state isolated across tests."""
    clear_modernization_policy_cache()
    yield
    clear_modernization_policy_cache()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()


def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires database)"
    )
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test (requires running server)"
    )
    config.addinivalue_line(
        "markers", "redis: mark test as requiring Redis connection"
    )


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that require database connection"
    )
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests that require running server"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration/e2e tests unless explicitly enabled."""
    run_integration = config.getoption("--run-integration")
    run_e2e = config.getoption("--run-e2e")

    skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
    skip_e2e = pytest.mark.skip(reason="need --run-e2e option to run")

    for item in items:
        if "integration" in item.keywords and not run_integration:
            item.add_marker(skip_integration)
        if "e2e" in item.keywords and not run_e2e:
            item.add_marker(skip_e2e)
