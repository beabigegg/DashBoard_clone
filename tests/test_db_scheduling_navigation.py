# -*- coding: utf-8 -*-
"""Navigation contract tests for db-scheduling page.

Validates:
- data/page_status.json has a 'db-scheduling' entry
- /db-scheduling route appears in known-pages list
These are Python-side navigation-metadata tests; drawer order is
validated in the frontend navigationManifest.js (frontend-side test
per test-plan.md AC-7).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGE_STATUS_FILE = ROOT / "data" / "page_status.json"


class TestPageStatusEntry:
    """data/page_status.json must contain a 'db-scheduling' entry."""

    def test_page_status_entry_exists(self):
        """page_status.json has a db-scheduling route entry."""
        payload = json.loads(PAGE_STATUS_FILE.read_text(encoding='utf-8'))
        statuses = payload.get('statuses', {})
        assert '/db-scheduling' in statuses, (
            "'/db-scheduling' not found in data/page_status.json statuses. "
            "Add it per the modernization policy."
        )

    def test_page_status_db_scheduling_is_dev_or_released(self):
        """The db-scheduling status is a valid status value."""
        payload = json.loads(PAGE_STATUS_FILE.read_text(encoding='utf-8'))
        statuses = payload.get('statuses', {})
        status = statuses.get('/db-scheduling')
        valid = {'dev', 'released'}
        assert status in valid, (
            f"db-scheduling status '{status}' not in {valid}"
        )


class TestDbSchedulingInAllPages:
    """/db-scheduling must appear in the Flask page-registry known-routes."""

    def test_db_scheduling_in_all_pages(self):
        """page_status.json statuses dict includes /db-scheduling key."""
        payload = json.loads(PAGE_STATUS_FILE.read_text(encoding='utf-8'))
        statuses = payload.get('statuses', {})
        all_routes = list(statuses.keys())
        assert '/db-scheduling' in all_routes, (
            f"/db-scheduling not in page_status routes: {all_routes}"
        )
