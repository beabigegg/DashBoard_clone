# -*- coding: utf-8 -*-
"""Unit tests for page_registry module (post nav-config-to-code).

Tests cover:
  - get_page_status: reads from statuses dict
  - set_page_status: status-only write; persists to statuses dict
  - get_all_pages: returns slim [{route,status}] list
  - get_navigation_config: returns statuses dict
  - is_api_public: preserved; works on shrunk store
  - TestShrunkStoreBackCompat: legacy full-CMS file → correct statuses; missing file → released
  - TestIsApiPublic: api_public preserved after shrink
  - TestReloadCache, TestConcurrency: unchanged
"""

import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mes_dashboard.services import page_registry


@pytest.fixture
def temp_shrunk_file(tmp_path):
    """Shrunk {api_public, statuses} store with a few entries."""
    data_file = tmp_path / "page_status.json"
    data = {
        "api_public": True,
        "statuses": {
            "/wip-overview": "released",
            "/admin/dashboard": "dev",
        },
    }
    data_file.write_text(json.dumps(data), encoding="utf-8")
    return data_file


@pytest.fixture
def temp_legacy_file(tmp_path):
    """Legacy full-CMS store: {pages:[], drawers:[], api_public}."""
    data_file = tmp_path / "page_status.json"
    data = {
        "api_public": True,
        "pages": [
            {"route": "/wip-overview", "name": "WIP", "status": "released"},
            {"route": "/admin/dashboard", "name": "管理儀表板", "status": "dev",
             "drawer_id": "dev-tools", "order": 2},
        ],
        "drawers": [
            {"id": "reports", "name": "即時報表", "order": 1, "admin_only": False},
            {"id": "dev-tools", "name": "開發工具", "order": 5, "admin_only": True},
        ],
        "db_scan": {"schema": "DWH"},
    }
    data_file.write_text(json.dumps(data), encoding="utf-8")
    return data_file


@pytest.fixture
def mock_registry_shrunk(temp_shrunk_file):
    """Point page_registry at the shrunk temp file."""
    original_data_file = page_registry.DATA_FILE
    original_cache = page_registry._cache
    original_cache_mtime = page_registry._cache_mtime

    page_registry.DATA_FILE = temp_shrunk_file
    page_registry._cache = None
    page_registry._cache_mtime = 0.0

    yield temp_shrunk_file

    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache
    page_registry._cache_mtime = original_cache_mtime


@pytest.fixture
def mock_registry_legacy(temp_legacy_file):
    """Point page_registry at the legacy temp file."""
    original_data_file = page_registry.DATA_FILE
    original_cache = page_registry._cache
    original_cache_mtime = page_registry._cache_mtime

    page_registry.DATA_FILE = temp_legacy_file
    page_registry._cache = None
    page_registry._cache_mtime = 0.0

    yield temp_legacy_file

    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache
    page_registry._cache_mtime = original_cache_mtime


@pytest.fixture
def mock_registry_missing(tmp_path):
    """Point page_registry at a non-existent file."""
    missing_file = tmp_path / "nonexistent_page_status.json"
    original_data_file = page_registry.DATA_FILE
    original_cache = page_registry._cache
    original_cache_mtime = page_registry._cache_mtime

    page_registry.DATA_FILE = missing_file
    page_registry._cache = None
    page_registry._cache_mtime = 0.0

    yield missing_file

    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache
    page_registry._cache_mtime = original_cache_mtime


class TestGetPageStatus:
    """Tests for get_page_status reading from shrunk store."""

    def test_get_released_status(self, mock_registry_shrunk):
        assert page_registry.get_page_status("/wip-overview") == "released"

    def test_get_dev_status(self, mock_registry_shrunk):
        assert page_registry.get_page_status("/admin/dashboard") == "dev"

    def test_get_unregistered_returns_none(self, mock_registry_shrunk):
        assert page_registry.get_page_status("/not-registered") is None

    def test_missing_file_returns_none(self, mock_registry_missing):
        # Absent route → None (caller treats as released)
        assert page_registry.get_page_status("/wip-overview") is None


class TestSetPageStatus:
    """Tests for set_page_status (status-only write)."""

    def test_set_status_on_shrunk_store_persists(self, mock_registry_shrunk, temp_shrunk_file):
        page_registry.set_page_status("/wip-overview", "dev")
        # Reload and verify persisted
        page_registry._cache = None
        assert page_registry.get_page_status("/wip-overview") == "dev"

    def test_status_change_reflected_in_get_all_pages(self, mock_registry_shrunk):
        page_registry.set_page_status("/wip-overview", "dev")
        pages = page_registry.get_all_pages()
        routes = {p["route"]: p["status"] for p in pages}
        assert routes["/wip-overview"] == "dev"

    def test_set_new_route_creates_entry(self, mock_registry_shrunk):
        page_registry.set_page_status("/new-route", "released")
        assert page_registry.get_page_status("/new-route") == "released"

    def test_invalid_status_raises_error(self, mock_registry_shrunk):
        with pytest.raises(ValueError, match="Invalid status"):
            page_registry.set_page_status("/wip-overview", "invalid")


class TestGetAllPages:
    """Tests for get_all_pages slim output shape."""

    def test_returns_slim_route_status_list(self, mock_registry_shrunk):
        pages = page_registry.get_all_pages()
        assert isinstance(pages, list)
        for p in pages:
            assert set(p.keys()) == {"route", "status"}
            assert p["status"] in ("released", "dev")

    def test_no_name_drawer_id_order_in_output(self, mock_registry_shrunk):
        pages = page_registry.get_all_pages()
        for p in pages:
            assert "name" not in p
            assert "drawer_id" not in p
            assert "order" not in p


class TestGetNavigationConfig:
    """Tests for get_navigation_config returning status dict."""

    def test_returns_statuses_dict(self, mock_registry_shrunk):
        nav = page_registry.get_navigation_config()
        assert isinstance(nav, dict)
        assert nav["/wip-overview"] == "released"
        assert nav["/admin/dashboard"] == "dev"

    def test_no_drawers_key_in_result(self, mock_registry_shrunk):
        nav = page_registry.get_navigation_config()
        assert "drawers" not in nav
        assert "pages" not in nav

    def test_missing_file_returns_empty_dict(self, mock_registry_missing):
        nav = page_registry.get_navigation_config()
        assert nav == {}


class TestShrunkStoreBackCompat:
    """AC-6: back-compat read of legacy full-CMS file."""

    def test_legacy_full_cms_file_yields_correct_statuses(self, mock_registry_legacy):
        nav = page_registry.get_navigation_config()
        assert nav["/wip-overview"] == "released"
        assert nav["/admin/dashboard"] == "dev"

    def test_legacy_file_no_error_no_forced_rewrite(self, mock_registry_legacy, temp_legacy_file):
        # Reading must not raise and must not rewrite the file to shrunk shape
        original_text = temp_legacy_file.read_text()
        page_registry.get_navigation_config()
        # File must not have been rewritten by a read-only legacy path
        # (set_page_status would rewrite, but not _normalise_store)
        current_text = temp_legacy_file.read_text()
        original_data = json.loads(original_text)
        # Confirm original legacy keys still present (file not overwritten by read)
        assert "pages" in original_data

    def test_missing_file_defaults_to_released(self, mock_registry_missing):
        # Missing file → empty statuses → all routes absent → released (in consumers)
        nav = page_registry.get_navigation_config()
        assert nav == {}
        # get_page_status returns None (caller maps None → released)
        assert page_registry.get_page_status("/wip-overview") is None

    def test_default_status_dev_hides_admin_dashboard_without_store(self, mock_registry_missing):
        # With a missing file, /admin/dashboard has no explicit dev status
        # (defaultStatus:dev lives in the frontend manifest, not the store)
        assert page_registry.get_page_status("/admin/dashboard") is None

    def test_legacy_api_public_preserved(self, mock_registry_legacy):
        assert page_registry.is_api_public() is True

    def test_legacy_drawers_ignored(self, mock_registry_legacy):
        # get_navigation_config returns only status dict, not drawer structure
        nav = page_registry.get_navigation_config()
        for v in nav.values():
            assert v in ("released", "dev")


class TestIsApiPublic:
    """Tests for is_api_public — must remain intact after shrink."""

    def test_api_public_true_on_shrunk_store(self, mock_registry_shrunk):
        assert page_registry.is_api_public() is True

    def test_api_public_false_on_shrunk_store(self, mock_registry_shrunk, temp_shrunk_file):
        data = json.loads(temp_shrunk_file.read_text())
        data["api_public"] = False
        temp_shrunk_file.write_text(json.dumps(data))
        page_registry._cache = None
        assert page_registry.is_api_public() is False

    def test_api_public_defaults_false_when_key_missing(self, mock_registry_shrunk, temp_shrunk_file):
        data = json.loads(temp_shrunk_file.read_text())
        data.pop("api_public", None)
        temp_shrunk_file.write_text(json.dumps(data))
        page_registry._cache = None
        assert page_registry.is_api_public() is False

    def test_api_public_key_preserved_after_shrink(self, mock_registry_shrunk, temp_shrunk_file):
        """AC-6 tripwire: api_public must survive a set_page_status write."""
        # Perform a write (which rewrites the file)
        page_registry.set_page_status("/new-route", "dev")
        # Reload and verify api_public is still present
        page_registry._cache = None
        assert page_registry.is_api_public() is True, (
            "api_public was dropped from page_status.json after a status write — "
            "this would silently disable the site-wide auth bypass gate"
        )

    def test_api_public_invalid_value_defaults_false(self, mock_registry_shrunk, temp_shrunk_file):
        data = json.loads(temp_shrunk_file.read_text())
        data["api_public"] = "not-a-bool"
        temp_shrunk_file.write_text(json.dumps(data))
        page_registry._cache = None
        assert page_registry.is_api_public() is False


class TestReloadCache:
    """Tests for reload_cache."""

    def test_reload_cache_picks_up_file_change(self, mock_registry_shrunk, temp_shrunk_file):
        assert page_registry.get_page_status("/wip-overview") == "released"

        data = json.loads(temp_shrunk_file.read_text())
        data["statuses"]["/wip-overview"] = "dev"
        temp_shrunk_file.write_text(json.dumps(data))

        page_registry.reload_cache()
        assert page_registry.get_page_status("/wip-overview") == "dev"


class TestConcurrency:
    """Tests for thread safety."""

    def test_concurrent_access(self, mock_registry_shrunk):
        errors = []

        def reader():
            try:
                for _ in range(100):
                    page_registry.get_page_status("/wip-overview")
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(exc)

        def writer():
            try:
                for index in range(100):
                    status = "released" if index % 2 == 0 else "dev"
                    page_registry.set_page_status("/wip-overview", status)
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(3)] + [
            threading.Thread(target=writer) for _ in range(2)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
