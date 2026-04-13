# -*- coding: utf-8 -*-
"""Pytest configuration for Playwright E2E tests."""

import os
import sys
from urllib.parse import urlsplit, urlunsplit

import pytest

# Add src and project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.conftest import _is_external_e2e_target


def _normalize_target_url(raw_base_url: str, raw_base_path: str) -> str:
    """Return a stable E2E target URL from env vars.

    Supports either:
    - E2E_BASE_URL=https://host
    - E2E_BASE_URL=https://host/root
    - E2E_BASE_URL=https://host + E2E_BASE_PATH=/root
    """
    parsed = urlsplit((raw_base_url or 'http://127.0.0.1:8080').strip())
    if not parsed.scheme or not parsed.netloc:
        raise pytest.UsageError(
            "E2E_BASE_URL must be an absolute URL, e.g. https://example.com or http://127.0.0.1:8080"
        )

    path_parts = []
    for part in (parsed.path, raw_base_path or ''):
        cleaned = str(part).strip()
        if cleaned and cleaned != '/':
            path_parts.append(cleaned.strip('/'))

    normalized_path = f"/{'/'.join(path_parts)}" if path_parts else ''
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, '', ''))


@pytest.fixture(scope="session")
def app_server() -> str:
    """Get the normalized base URL for E2E testing."""
    return _normalize_target_url(
        os.environ.get('E2E_BASE_URL', 'http://127.0.0.1:8080'),
        os.environ.get('E2E_BASE_PATH', ''),
    )


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """Configure browser context for tests."""
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "zh-TW",
    }


def pytest_configure(config):
    """Add custom markers for E2E tests."""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test (requires running server)"
    )
    config.addinivalue_line(
        "markers", "redis: mark test as requiring Redis connection"
    )


@pytest.fixture(scope="session")
def api_base_url(app_server):
    """Get the API base URL."""
    return f"{app_server}/api"


@pytest.fixture(scope="session")
def health_url(app_server):
    """Get the health check URL."""
    return f"{app_server}/health"


@pytest.fixture(autouse=True)
def skip_local_only_on_external_target(request):
    """Auto-skip tests marked local_only when running against an external E2E target."""
    if request.node.get_closest_marker("local_only") and _is_external_e2e_target():
        pytest.skip("Skipped: local_only test against external E2E target")
