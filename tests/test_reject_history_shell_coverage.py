# -*- coding: utf-8 -*-
"""Governance coverage tests for reject-history shell integration."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTE_CONTRACTS_FILE = ROOT / 'frontend' / 'src' / 'portal-shell' / 'routeContracts.js'
NATIVE_REGISTRY_FILE = ROOT / 'frontend' / 'src' / 'portal-shell' / 'nativeModuleRegistry.js'
PAGE_STATUS_FILE = ROOT / 'data' / 'page_status.json'


def test_reject_history_route_contract_entry_exists():
    text = ROUTE_CONTRACTS_FILE.read_text(encoding='utf-8')

    assert "'/reject-history'" in text
    assert "routeId: 'reject-history'" in text
    assert "title: '報廢歷史查詢'" in text


def test_reject_history_native_loader_entry_exists():
    text = NATIVE_REGISTRY_FILE.read_text(encoding='utf-8')

    assert "'/reject-history'" in text
    assert "import('../reject-history/App.vue')" in text


def test_reject_history_page_status_entry_exists():
    payload = json.loads(PAGE_STATUS_FILE.read_text(encoding='utf-8'))
    pages = payload.get('pages', [])

    entry = next((item for item in pages if item.get('route') == '/reject-history'), None)
    assert entry is not None
    assert entry.get('drawer_id')
    assert isinstance(entry.get('order'), int)
