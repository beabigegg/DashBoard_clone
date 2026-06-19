# -*- coding: utf-8 -*-
"""Contract test: DOWNTIME_USE_UNIFIED_JOB env default pinned to 'off' (AC-6).

Verifies that:
1. The flag is documented in contracts/env/env-contract.md
2. The flag appears in contracts/env/.env.example.template with default 'off'
3. contracts/env/env.schema.json has the flag with enum + default='off'

Per test-discipline: pin exact default value, not just var name presence.
Pattern mirrors tests/contract/test_env_material_trace_flag.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_CONTRACTS_DIR = Path(__file__).parent.parent.parent / "contracts" / "env"
_ENV_CONTRACT = _CONTRACTS_DIR / "env-contract.md"
_ENV_EXAMPLE = _CONTRACTS_DIR / ".env.example.template"
_ENV_SCHEMA = _CONTRACTS_DIR / "env.schema.json"

_EXPECTED_KEY = "DOWNTIME_USE_UNIFIED_JOB"
_EXPECTED_DEFAULT = "off"


class TestDowntimeUnifiedFlagInEnvContract:
    """AC-6: Flag must be documented in env-contract.md."""

    def test_flag_in_env_contract_md(self):
        """DOWNTIME_USE_UNIFIED_JOB must appear in env-contract.md."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        assert _EXPECTED_KEY in content, (
            f"{_EXPECTED_KEY} not found in contracts/env/env-contract.md (AC-6)"
        )

    def test_flag_documented_with_default_off_in_contract_md(self):
        """env-contract.md must document the 'off' default for the flag."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        key_idx = content.find(_EXPECTED_KEY)
        assert key_idx != -1, f"{_EXPECTED_KEY} not in env-contract.md"
        section = content[key_idx : key_idx + 500]
        assert "off" in section.lower(), (
            f"env-contract.md: expected 'off' default near {_EXPECTED_KEY} section"
        )


class TestDowntimeUnifiedFlagInEnvExample:
    """AC-6: Flag must be present with default=off in .env.example.template."""

    def test_flag_in_env_example_template(self):
        """DOWNTIME_USE_UNIFIED_JOB= line must exist in .env.example.template."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        assert _EXPECTED_KEY + "=" in content, (
            f"{_EXPECTED_KEY}= not found in contracts/env/.env.example.template (AC-6)"
        )

    def test_flag_default_is_off_in_env_example_template(self):
        """Default value in .env.example.template must be exactly 'off'."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        assert f"{_EXPECTED_KEY}=off" in content, (
            f"Expected '{_EXPECTED_KEY}=off' in .env.example.template (AC-6); "
            f"default must be 'off' to ensure zero-regression on deploy"
        )


class TestDowntimeUnifiedFlagInSchema:
    """AC-6: Flag must be registered in env.schema.json with enum + default='off'."""

    def test_flag_in_schema_json(self):
        """DOWNTIME_USE_UNIFIED_JOB must be a property in env.schema.json."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        assert _EXPECTED_KEY in schema.get("properties", {}), (
            f"{_EXPECTED_KEY} not in env.schema.json properties (AC-6)"
        )

    def test_flag_default_is_off_in_schema(self):
        """Default in env.schema.json must be exactly 'off'."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"].get(_EXPECTED_KEY, {})
        assert prop.get("default") == _EXPECTED_DEFAULT, (
            f"env.schema.json: {_EXPECTED_KEY} default must be '{_EXPECTED_DEFAULT}', "
            f"got {prop.get('default')!r} (AC-6)"
        )

    def test_flag_enum_includes_off_and_on(self):
        """Schema enum must include both 'off' and 'on' values."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"].get(_EXPECTED_KEY, {})
        enum = prop.get("enum", [])
        assert "off" in enum, f"Schema enum missing 'off': {enum}"
        assert "on" in enum, f"Schema enum missing 'on': {enum}"
