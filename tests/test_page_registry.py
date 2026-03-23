# -*- coding: utf-8 -*-
"""Unit tests for page_registry module."""

import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services import page_registry


@pytest.fixture
def temp_data_file(tmp_path):
    """Create a temporary legacy data file for migration tests."""
    data_file = tmp_path / "page_status.json"
    initial_data = {
        "pages": [
            {"route": "/", "name": "Home", "status": "released"},
            {"route": "/wip-overview", "name": "WIP Overview", "status": "released"},
            {"route": "/tables", "name": "Tables", "status": "dev"},
            {"route": "/dev-page", "name": "Dev Page", "status": "dev"},
        ],
        "api_public": True,
    }
    data_file.write_text(json.dumps(initial_data), encoding="utf-8")
    return data_file


@pytest.fixture
def mock_registry(temp_data_file):
    """Mock page_registry to use temp file."""
    original_data_file = page_registry.DATA_FILE
    original_cache = page_registry._cache
    original_cache_mtime = page_registry._cache_mtime

    page_registry.DATA_FILE = temp_data_file
    page_registry._cache = None
    page_registry._cache_mtime = 0.0

    yield temp_data_file

    page_registry.DATA_FILE = original_data_file
    page_registry._cache = original_cache
    page_registry._cache_mtime = original_cache_mtime


class TestSchemaMigration:
    """Tests for first-run drawers migration."""

    def test_migration_adds_drawers_and_assignments(self, mock_registry):
        drawers = page_registry.get_all_drawers()
        drawer_ids = [drawer["id"] for drawer in drawers]
        assert drawer_ids == ["reports", "queries", "dev-tools"]

        pages = page_registry.get_all_pages()
        page_by_route = {page["route"]: page for page in pages}

        assert page_by_route["/wip-overview"]["drawer_id"] == "reports"
        assert page_by_route["/wip-overview"]["order"] == 1
        assert page_by_route["/tables"]["drawer_id"] == "queries"
        assert page_by_route["/tables"]["order"] == 1

        # Admin tools should be backfilled from legacy hardcoded sidebar mapping.
        assert page_by_route["/admin/pages"]["drawer_id"] == "dev-tools"
        assert page_by_route["/admin/dashboard"]["drawer_id"] == "dev-tools"
        assert page_by_route["/admin/performance"]["drawer_id"] == "dev-tools"

    def test_subsequent_load_does_not_reset_drawers(self, mock_registry):
        page_registry.get_all_drawers()
        page_registry.create_drawer("custom", order=10, admin_only=False)

        page_registry.reload_cache()
        drawers = page_registry.get_all_drawers()
        assert any(drawer["id"] == "custom" for drawer in drawers)


class TestGetPageStatus:
    """Tests for get_page_status function."""

    def test_get_released_page_status(self, mock_registry):
        status = page_registry.get_page_status("/")
        assert status == "released"

    def test_get_dev_page_status(self, mock_registry):
        status = page_registry.get_page_status("/dev-page")
        assert status == "dev"

    def test_get_unregistered_page_status(self, mock_registry):
        status = page_registry.get_page_status("/not-registered")
        assert status is None


class TestSetPageStatus:
    """Tests for set_page_status function."""

    def test_update_existing_page_status(self, mock_registry):
        page_registry.set_page_status("/dev-page", "released")
        assert page_registry.get_page_status("/dev-page") == "released"

    def test_set_page_drawer_and_order(self, mock_registry):
        page_registry.set_page_status("/dev-page", "dev", drawer_id="queries", order=9)
        pages = page_registry.get_all_pages()
        dev_page = next(page for page in pages if page["route"] == "/dev-page")
        assert dev_page["drawer_id"] == "queries"
        assert dev_page["order"] == 9

    def test_clear_page_drawer_and_order(self, mock_registry):
        page_registry.set_page_status("/dev-page", "dev", drawer_id="queries", order=9)
        page_registry.set_page_status("/dev-page", "dev", drawer_id=None, order=None)
        pages = page_registry.get_all_pages()
        dev_page = next(page for page in pages if page["route"] == "/dev-page")
        assert "drawer_id" not in dev_page
        assert "order" not in dev_page

    def test_set_invalid_drawer_raises_error(self, mock_registry):
        with pytest.raises(ValueError, match="Drawer not found"):
            page_registry.set_page_status("/dev-page", "dev", drawer_id="not-exists")

    def test_invalid_status_raises_error(self, mock_registry):
        with pytest.raises(ValueError, match="Invalid status"):
            page_registry.set_page_status("/", "invalid")


class TestDrawerCrud:
    """Tests for drawer CRUD functions."""

    def test_create_drawer(self, mock_registry):
        created = page_registry.create_drawer("Custom Drawer", order=4, admin_only=True)
        assert created["name"] == "Custom Drawer"
        assert created["order"] == 4
        assert created["admin_only"] is True

    def test_create_duplicate_drawer_name_raises_conflict(self, mock_registry):
        with pytest.raises(page_registry.DrawerConflictError):
            page_registry.create_drawer("報表類", order=4)

    def test_update_drawer(self, mock_registry):
        updated = page_registry.update_drawer(
            "reports",
            name="報表中心",
            order=7,
            admin_only=True,
        )
        assert updated["name"] == "報表中心"
        assert updated["order"] == 7
        assert updated["admin_only"] is True

    def test_delete_drawer_rejects_assigned_pages(self, mock_registry):
        with pytest.raises(page_registry.DrawerConflictError, match="assigned pages"):
            page_registry.delete_drawer("reports")

    def test_delete_empty_drawer(self, mock_registry):
        created = page_registry.create_drawer("Temporary", order=8)
        page_registry.delete_drawer(created["id"])
        drawers = page_registry.get_all_drawers()
        assert all(drawer["id"] != created["id"] for drawer in drawers)


class TestNavigationConfig:
    """Tests for navigation config generation."""

    def test_navigation_config_grouped_and_sorted(self, mock_registry):
        page_registry.set_page_status("/dev-page", "dev", drawer_id="queries", order=5)
        nav = page_registry.get_navigation_config()

        assert [drawer["id"] for drawer in nav] == ["reports", "queries", "dev-tools"]

        reports = next(drawer for drawer in nav if drawer["id"] == "reports")
        assert [page["route"] for page in reports["pages"]] == ["/wip-overview"]
        assert "frame_id" not in reports["pages"][0]
        assert "tool_src" not in reports["pages"][0]

        queries = next(drawer for drawer in nav if drawer["id"] == "queries")
        assert queries["pages"][0]["route"] == "/tables"
        assert queries["pages"][-1]["route"] == "/dev-page"

        dev_tools = next(drawer for drawer in nav if drawer["id"] == "dev-tools")
        assert all("frame_id" not in page for page in dev_tools["pages"])
        assert all("tool_src" not in page for page in dev_tools["pages"])


class TestIsApiPublic:
    """Tests for is_api_public function."""

    def test_api_public_true(self, mock_registry):
        assert page_registry.is_api_public() is True

    def test_api_public_false(self, mock_registry, temp_data_file):
        data = json.loads(temp_data_file.read_text())
        data["api_public"] = False
        temp_data_file.write_text(json.dumps(data))
        page_registry._cache = None

        assert page_registry.is_api_public() is False

    def test_api_public_defaults_false_when_key_missing(self, mock_registry, temp_data_file):
        data = json.loads(temp_data_file.read_text())
        data.pop("api_public", None)
        temp_data_file.write_text(json.dumps(data))
        page_registry._cache = None

        assert page_registry.is_api_public() is False

    def test_api_public_invalid_value_defaults_false(self, mock_registry, temp_data_file):
        data = json.loads(temp_data_file.read_text())
        data["api_public"] = "not-a-bool"
        temp_data_file.write_text(json.dumps(data))
        page_registry._cache = None

        assert page_registry.is_api_public() is False


class TestReloadCache:
    """Tests for reload_cache function."""

    def test_reload_cache(self, mock_registry, temp_data_file):
        assert page_registry.get_page_status("/") == "released"

        data = json.loads(temp_data_file.read_text())
        home = next(page for page in data["pages"] if page["route"] == "/")
        home["status"] = "dev"
        temp_data_file.write_text(json.dumps(data))

        # Note: _load() has mtime-based invalidation that may auto-detect
        # the file change, so we only assert post-reload behavior.
        page_registry.reload_cache()
        assert page_registry.get_page_status("/") == "dev"


class TestConcurrency:
    """Tests for thread safety."""

    def test_concurrent_access(self, mock_registry):
        errors = []

        def reader():
            try:
                for _ in range(100):
                    page_registry.get_page_status("/")
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(exc)

        def writer():
            try:
                for index in range(100):
                    status = "released" if index % 2 == 0 else "dev"
                    page_registry.set_page_status("/", status)
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
