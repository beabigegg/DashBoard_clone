# -*- coding: utf-8 -*-
"""Pytest configuration and fixtures for MES Dashboard tests."""

import logging
import os
import sys
from urllib.parse import urlsplit

import pytest

# Add the src directory and project root to Python path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, 'src'))
sys.path.insert(0, _PROJECT_ROOT)
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


def _is_external_e2e_target() -> bool:
    """Return True when e2e tests target a remote/external deployment."""
    explicit = os.environ.get('E2E_EXTERNAL_TARGET', '').strip().lower()
    if explicit in {'1', 'true', 'yes', 'on'}:
        return True
    if explicit in {'0', 'false', 'no', 'off'}:
        return False

    host = urlsplit(os.environ.get('E2E_BASE_URL', 'http://127.0.0.1:8080')).hostname or ''
    return host not in {'127.0.0.1', 'localhost', '0.0.0.0'}


def _load_dotenv_if_present():
    """Load .env file into os.environ for integration/e2e tests.

    Uses setdefault so explicit env vars (e.g. FLASK_ENV=testing set above)
    take precedence over .env values.
    """
    env_path = os.path.join(_PROJECT_ROOT, '.env')
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            # Strip inline comments (e.g. "4  # PRD: 5" → "4")
            if '#' in value:
                value = value[:value.index('#')]
            os.environ.setdefault(key.strip(), value.strip())


# When --run-integration or --run-e2e is passed, load .env BEFORE database module
# import so DB_HOST/DB_USER etc. are available for CONNECTION_STRING construction.
# The database config module explicitly skips .env under pytest (to isolate unit tests),
# so we pre-populate the env vars here for integration/e2e runs.
if '--run-integration' in sys.argv or '--run-e2e' in sys.argv:
    _load_dotenv_if_present()

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


@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    """Reset circuit breaker singleton between tests to prevent order-dependency."""
    import mes_dashboard.core.circuit_breaker as cb_mod
    cb_mod._DATABASE_CIRCUIT_BREAKER = None
    yield
    cb_mod._DATABASE_CIRCUIT_BREAKER = None


@pytest.fixture(autouse=True)
def _restore_logger_propagation():
    """Restore mes_dashboard logger propagation after tests that call create_app().

    create_app() sets logger.propagate = False, which is correct for production
    but breaks caplog in subsequent tests (caplog relies on propagation to root).
    """
    yield
    logging.getLogger('mes_dashboard').propagate = True


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
        "markers", "local_e2e: mark test as requiring an in-process local Flask app"
    )
    config.addinivalue_line(
        "markers", "redis: mark test as requiring Redis connection"
    )
    config.addinivalue_line(
        "markers", "stress: mark test as stress/load test (requires --run-stress)"
    )
    config.addinivalue_line(
        "markers", "load: mark test as load test (requires --run-stress)"
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
    parser.addoption(
        "--run-stress",
        action="store_true",
        default=False,
        help="Run stress/load tests that require running server"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration/e2e tests unless explicitly enabled."""
    run_integration = config.getoption("--run-integration")
    run_e2e = config.getoption("--run-e2e")

    run_stress = config.getoption("--run-stress")

    skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
    skip_e2e = pytest.mark.skip(reason="need --run-e2e option to run")
    skip_stress = pytest.mark.skip(reason="need --run-stress option to run")
    skip_local_e2e = pytest.mark.skip(
        reason="requires local in-process app; skip when targeting an external E2E deployment"
    )
    external_e2e_target = _is_external_e2e_target()

    for item in items:
        # Use get_closest_marker to avoid matching "integration_real" via keyword string-in check
        if item.get_closest_marker("integration") and not item.get_closest_marker("integration_real") and not run_integration:
            item.add_marker(skip_integration)
        if "e2e" in item.keywords and not run_e2e:
            item.add_marker(skip_e2e)
        if "local_e2e" in item.keywords and external_e2e_target:
            item.add_marker(skip_local_e2e)
        if (item.get_closest_marker("stress") or item.get_closest_marker("load")) and not run_stress:
            item.add_marker(skip_stress)
