# -*- coding: utf-8 -*-
"""Tests for portal navigation migration contract helpers."""

from __future__ import annotations

import json
from pathlib import Path

from mes_dashboard.services.navigation_contract import validate_drawer_page_contract


ROOT = Path(__file__).resolve().parent.parent
PAGE_STATUS_FILE = ROOT / "data" / "page_status.json"


def test_current_page_status_contract_has_no_validation_errors():
    payload = json.loads(PAGE_STATUS_FILE.read_text(encoding="utf-8"))
    errors = validate_drawer_page_contract(payload)
    assert errors == []
