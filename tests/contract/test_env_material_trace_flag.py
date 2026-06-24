# -*- coding: utf-8 -*-
"""Contract test: MATERIAL_TRACE_USE_UNIFIED_JOB env default pinned to 'off' (AC-7).

Verifies that:
1. The flag is documented in contracts/env/env-contract.md
2. The flag appears in contracts/env/.env.example.template with default 'off'
3. contracts/env/env.schema.json has the flag with enum + default='off'

Per test-discipline: pin exact default value, not just var name presence.
Pattern mirrors tests/contract/test_env_duckdb_job_dir.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_CONTRACTS_DIR = Path(__file__).parent.parent.parent / "contracts" / "env"
_ENV_CONTRACT = _CONTRACTS_DIR / "env-contract.md"
_ENV_EXAMPLE = _CONTRACTS_DIR / ".env.example.template"
_ENV_SCHEMA = _CONTRACTS_DIR / "env.schema.json"

_EXPECTED_KEY = "MATERIAL_TRACE_USE_UNIFIED_JOB"
_EXPECTED_DEFAULT = "on"


class TestMaterialTraceFlagInEnvContract:
    """AC-7: Flag must be documented in env-contract.md."""

    def test_flag_in_env_contract_md(self):
        """MATERIAL_TRACE_USE_UNIFIED_JOB must appear in env-contract.md."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        assert _EXPECTED_KEY in content, (
            f"{_EXPECTED_KEY} not found in contracts/env/env-contract.md (AC-7)"
        )

    def test_flag_documented_with_default_off_in_contract_md(self):
        """env-contract.md must document the 'off' default for the flag."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        # Find the section that mentions the flag and check 'off' is nearby
        key_idx = content.find(_EXPECTED_KEY)
        assert key_idx != -1, f"{_EXPECTED_KEY} not in env-contract.md"
        # The default 'off' should appear within reasonable proximity of the key
        section = content[key_idx: key_idx + 500]
        assert "off" in section.lower(), (
            f"env-contract.md: expected 'off' default near {_EXPECTED_KEY} section"
        )


class TestMaterialTraceFlagInEnvExample:
    """AC-7: Flag must be present with default=off in .env.example.template."""

    def test_flag_in_env_example_template(self):
        """MATERIAL_TRACE_USE_UNIFIED_JOB= line must exist in .env.example.template."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        assert _EXPECTED_KEY + "=" in content, (
            f"{_EXPECTED_KEY}= not found in contracts/env/.env.example.template (AC-7)"
        )

    def test_flag_example_default_is_off(self):
        """The flag's example line must carry value 'off' (exact default pin)."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith(_EXPECTED_KEY + "="):
                value = stripped.split("=", 1)[1].strip()
                assert value == _EXPECTED_DEFAULT, (
                    f"{_EXPECTED_KEY} default in .env.example.template must be "
                    f"'{_EXPECTED_DEFAULT}', got '{value}' (AC-7)"
                )
                return
        pytest.fail(
            f"{_EXPECTED_KEY}= line not found in .env.example.template (AC-7)"
        )


class TestMaterialTraceFlagInEnvSchema:
    """AC-7: Flag must be in env.schema.json with enum + default='off'."""

    def _schema(self) -> dict:
        return json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))

    def test_flag_default_off_pinned(self):
        """AC-7 core pin: schema default must be exactly 'off'."""
        prop = self._schema().get("properties", {}).get(_EXPECTED_KEY, {})
        default = prop.get("default")
        assert default == _EXPECTED_DEFAULT, (
            f"env.schema.json {_EXPECTED_KEY}.default must be '{_EXPECTED_DEFAULT}', "
            f"got {default!r} (AC-7 exact default pin)"
        )

    def test_flag_schema_has_enum(self):
        """Schema enum must be present (required by env test-discipline rule)."""
        prop = self._schema().get("properties", {}).get(_EXPECTED_KEY, {})
        assert "enum" in prop, (
            f"{_EXPECTED_KEY} schema entry must have 'enum' key for machine enum validation (AC-7)"
        )

    def test_flag_schema_enum_contains_off_and_on(self):
        """Enum must include both 'off' and 'on'."""
        prop = self._schema().get("properties", {}).get(_EXPECTED_KEY, {})
        enum_vals = prop.get("enum", [])
        assert "off" in enum_vals, f"'off' must be in {_EXPECTED_KEY} enum, got {enum_vals}"
        assert "on" in enum_vals, f"'on' must be in {_EXPECTED_KEY} enum, got {enum_vals}"

    def test_flag_schema_type_is_string(self):
        """Schema type must be 'string' (standard feature-flag pattern)."""
        prop = self._schema().get("properties", {}).get(_EXPECTED_KEY, {})
        assert prop.get("type") == "string", (
            f"{_EXPECTED_KEY} schema type must be 'string', got {prop.get('type')!r}"
        )

    def test_flag_schema_has_description(self):
        """Schema entry should carry a description (auditing aid)."""
        prop = self._schema().get("properties", {}).get(_EXPECTED_KEY, {})
        assert "description" in prop, (
            f"{_EXPECTED_KEY} schema entry should have a 'description' field"
        )
