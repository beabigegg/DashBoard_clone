# -*- coding: utf-8 -*-
"""Pytest configuration for Playwright E2E tests."""

import pytest
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


@pytest.fixture(scope="session")
def app_server() -> str:
    """Get the base URL for E2E testing.

    Uses environment variable E2E_BASE_URL or defaults to production server.
    """
    return os.environ.get('E2E_BASE_URL', 'http://127.0.0.1:5000')


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
