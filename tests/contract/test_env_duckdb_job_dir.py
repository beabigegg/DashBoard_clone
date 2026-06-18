"""Contract tests for DUCKDB_JOB_DIR env variable (AC-6).

Pins DUCKDB_JOB_DIR name AND default value across all three contract files:
- contracts/env/env-contract.md
- contracts/env/.env.example.template
- contracts/env/env.schema.json

Per D4, the default must contain "duckdb_jobs".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_CONTRACTS_DIR = Path(__file__).parent.parent.parent / "contracts" / "env"
_ENV_CONTRACT = _CONTRACTS_DIR / "env-contract.md"
_ENV_EXAMPLE = _CONTRACTS_DIR / ".env.example.template"
_ENV_SCHEMA = _CONTRACTS_DIR / "env.schema.json"

_EXPECTED_KEY = "DUCKDB_JOB_DIR"
_EXPECTED_DEFAULT_FRAGMENT = "duckdb_jobs"  # D4 pin


class TestDuckdbJobDirInEnvContract:
    def test_duckdb_job_dir_in_env_contract(self):
        """DUCKDB_JOB_DIR must be documented in env-contract.md."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        assert _EXPECTED_KEY in content, (
            f"{_EXPECTED_KEY} not found in {_ENV_CONTRACT.name}; "
            "contract must document this var (AC-6)"
        )

    def test_duckdb_job_dir_deprecation_notice_not_present(self):
        """DUCKDB_JOB_DIR is a NEW var, not deprecated — must not carry Deprecated tag."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        # Find the DUCKDB_JOB_DIR section.
        idx = content.find(_EXPECTED_KEY)
        assert idx != -1
        # Check surrounding ~500 chars for deprecation marker.
        section = content[idx : idx + 500]
        assert "Deprecated" not in section or "DUCKDB_JOB_DIR" == _EXPECTED_KEY, (
            "DUCKDB_JOB_DIR should NOT be marked Deprecated"
        )


class TestDuckdbJobDirInEnvExample:
    def test_duckdb_job_dir_in_env_example(self):
        """DUCKDB_JOB_DIR= line must exist in .env.example.template."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        assert _EXPECTED_KEY + "=" in content, (
            f"{_EXPECTED_KEY}= not found in {_ENV_EXAMPLE.name} (AC-6)"
        )

    def test_duckdb_job_dir_example_line_contains_default(self):
        """The DUCKDB_JOB_DIR= line must contain the default value fragment."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        for line in content.splitlines():
            if line.startswith(_EXPECTED_KEY + "="):
                assert _EXPECTED_DEFAULT_FRAGMENT in line, (
                    f"DUCKDB_JOB_DIR example line missing '{_EXPECTED_DEFAULT_FRAGMENT}': {line!r}"
                )
                break
        else:
            pytest.fail(f"{_EXPECTED_KEY}= line not found in {_ENV_EXAMPLE.name}")


class TestDuckdbJobDirInEnvSchema:
    def test_duckdb_job_dir_in_env_schema(self):
        """DUCKDB_JOB_DIR must exist as a property in env.schema.json."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        properties = schema.get("properties", {})
        assert _EXPECTED_KEY in properties, (
            f"{_EXPECTED_KEY} not found in env.schema.json properties (AC-6)"
        )

    def test_duckdb_job_dir_schema_has_string_type(self):
        """DUCKDB_JOB_DIR property must have type: string."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"].get(_EXPECTED_KEY, {})
        assert prop.get("type") == "string", (
            f"DUCKDB_JOB_DIR schema type must be 'string', got {prop.get('type')!r}"
        )

    def test_duckdb_job_dir_default_value_matches_design(self):
        """AC-6: Default value in schema must contain 'duckdb_jobs' (D4 pin)."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"].get(_EXPECTED_KEY, {})
        default = prop.get("default", "")
        assert _EXPECTED_DEFAULT_FRAGMENT in str(default), (
            f"DUCKDB_JOB_DIR schema default must contain '{_EXPECTED_DEFAULT_FRAGMENT}', "
            f"got {default!r} (D4 pin, AC-6)"
        )

    def test_duckdb_job_dir_schema_has_description(self):
        """DUCKDB_JOB_DIR property should have a description."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"].get(_EXPECTED_KEY, {})
        assert "description" in prop, "DUCKDB_JOB_DIR schema entry should have a description"
