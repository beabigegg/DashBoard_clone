# -*- coding: utf-8 -*-
"""Shared field contracts for UI/API/export mapping."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CONTRACTS_PATH = Path(__file__).resolve().parents[3] / "shared" / "field_contracts.json"


@lru_cache(maxsize=1)
def _load_contracts() -> dict[str, Any]:
    with _CONTRACTS_PATH.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return payload if isinstance(payload, dict) else {}


def get_page_contract(page: str, section: str) -> list[dict[str, Any]]:
    """Return contract list for a page section.

    Args:
        page: Page key, e.g. ``job_query``.
        section: Contract section key, e.g. ``export``.
    """
    page_contract = _load_contracts().get(page, {})
    fields = page_contract.get(section, []) if isinstance(page_contract, dict) else []
    return fields if isinstance(fields, list) else []


def get_export_headers(page: str) -> list[str]:
    """Return export headers in canonical order for a page."""
    return [field.get("export_header", "") for field in get_page_contract(page, "export") if field.get("export_header")]


def get_export_api_keys(page: str) -> list[str]:
    """Return export API keys in canonical order for a page."""
    return [field.get("api_key", "") for field in get_page_contract(page, "export") if field.get("api_key")]
