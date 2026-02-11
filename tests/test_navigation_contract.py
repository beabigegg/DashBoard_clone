# -*- coding: utf-8 -*-
"""Tests for portal navigation migration contract helpers."""

from __future__ import annotations

import json
from pathlib import Path

from mes_dashboard.services.navigation_contract import (
    compute_drawer_visibility,
    validate_drawer_page_contract,
)


ROOT = Path(__file__).resolve().parent.parent
PAGE_STATUS_FILE = ROOT / "data" / "page_status.json"
BASELINE_VISIBILITY_FILE = ROOT / "docs" / "migration" / "portal-no-iframe" / "baseline_drawer_visibility.json"


def test_current_page_status_contract_has_no_validation_errors():
    payload = json.loads(PAGE_STATUS_FILE.read_text(encoding="utf-8"))
    errors = validate_drawer_page_contract(payload)
    assert errors == []


def test_baseline_visibility_matches_computed_current_state():
    payload = json.loads(PAGE_STATUS_FILE.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE_VISIBILITY_FILE.read_text(encoding="utf-8"))

    assert baseline["admin"] == compute_drawer_visibility(payload, is_admin=True)
    assert baseline["non_admin"] == compute_drawer_visibility(payload, is_admin=False)
