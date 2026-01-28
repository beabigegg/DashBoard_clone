# -*- coding: utf-8 -*-
"""Unit tests for page_registry module."""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services import page_registry


@pytest.fixture
def temp_data_file(tmp_path):
    """Create a temporary data file for testing."""
    data_file = tmp_path / "page_status.json"
    initial_data = {
        "pages": [
            {"route": "/", "name": "Home", "status": "released"},
            {"route": "/dev-page", "name": "Dev Page", "status": "dev"},
        ],
        "api_public": True
    }
    data_file.write_text(json.dumps(initial_data), encoding="utf-8")
    return data_file


@pytest.fixture
def mock_registry(temp_data_file):
    """Mock page_registry to use temp file."""
    original_data_file = page_registry.DATA_FILE
    original_cache = page_registry._cache

    page_registry.DATA_FILE = temp_data_file
    page_registry._cache = None  # Clear cache

    yield temp_data_file

    # Restore original
    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache


class TestGetPageStatus:
    """Tests for get_page_status function."""

    def test_get_released_page_status(self, mock_registry):
        """Test getting status of released page."""
        status = page_registry.get_page_status("/")
        assert status == "released"

    def test_get_dev_page_status(self, mock_registry):
        """Test getting status of dev page."""
        status = page_registry.get_page_status("/dev-page")
        assert status == "dev"

    def test_get_unregistered_page_status(self, mock_registry):
        """Test getting status of unregistered page returns None."""
        status = page_registry.get_page_status("/not-registered")
        assert status is None


class TestIsPageRegistered:
    """Tests for is_page_registered function."""

    def test_registered_page(self, mock_registry):
        """Test checking registered page."""
        assert page_registry.is_page_registered("/") is True

    def test_unregistered_page(self, mock_registry):
        """Test checking unregistered page."""
        assert page_registry.is_page_registered("/not-here") is False


class TestSetPageStatus:
    """Tests for set_page_status function."""

    def test_update_existing_page(self, mock_registry):
        """Test updating existing page status."""
        page_registry.set_page_status("/", "dev")
        assert page_registry.get_page_status("/") == "dev"

    def test_add_new_page(self, mock_registry):
        """Test adding new page."""
        page_registry.set_page_status("/new-page", "released", "New Page")
        assert page_registry.get_page_status("/new-page") == "released"

    def test_invalid_status_raises_error(self, mock_registry):
        """Test setting invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid status"):
            page_registry.set_page_status("/", "invalid")

    def test_update_page_name(self, mock_registry):
        """Test updating page name."""
        page_registry.set_page_status("/", "released", "New Name")
        pages = page_registry.get_all_pages()
        home = next(p for p in pages if p["route"] == "/")
        assert home["name"] == "New Name"


class TestGetAllPages:
    """Tests for get_all_pages function."""

    def test_get_all_pages(self, mock_registry):
        """Test getting all pages."""
        pages = page_registry.get_all_pages()
        assert len(pages) == 2
        routes = [p["route"] for p in pages]
        assert "/" in routes
        assert "/dev-page" in routes


class TestIsApiPublic:
    """Tests for is_api_public function."""

    def test_api_public_true(self, mock_registry):
        """Test API public flag when true."""
        assert page_registry.is_api_public() is True

    def test_api_public_false(self, mock_registry, temp_data_file):
        """Test API public flag when false."""
        data = json.loads(temp_data_file.read_text())
        data["api_public"] = False
        temp_data_file.write_text(json.dumps(data))
        page_registry._cache = None  # Clear cache

        assert page_registry.is_api_public() is False


class TestReloadCache:
    """Tests for reload_cache function."""

    def test_reload_cache(self, mock_registry, temp_data_file):
        """Test reloading cache from disk."""
        # First load
        assert page_registry.get_page_status("/") == "released"

        # Modify file directly
        data = json.loads(temp_data_file.read_text())
        data["pages"][0]["status"] = "dev"
        temp_data_file.write_text(json.dumps(data))

        # Cache still has old value
        assert page_registry.get_page_status("/") == "released"

        # After reload, should have new value
        page_registry.reload_cache()
        assert page_registry.get_page_status("/") == "dev"


class TestConcurrency:
    """Tests for thread safety."""

    def test_concurrent_access(self, mock_registry):
        """Test concurrent read/write operations."""
        import threading

        errors = []

        def reader():
            try:
                for _ in range(100):
                    page_registry.get_page_status("/")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    status = "released" if i % 2 == 0 else "dev"
                    page_registry.set_page_status("/", status)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=reader) for _ in range(3)
        ] + [
            threading.Thread(target=writer) for _ in range(2)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
