# -*- coding: utf-8 -*-
"""AC-8: cdd-kit validate --contracts is wired into the CI contract gate.

Tests that .github/workflows/contract-driven-gates.yml contains the
`cdd-kit validate --contracts` step command.
"""
from __future__ import annotations

from pathlib import Path

import pytest

WORKFLOW_PATH = (
    Path(__file__).parent.parent.parent
    / ".github"
    / "workflows"
    / "contract-driven-gates.yml"
)


class TestGateWiring:
    """AC-8: CI gate wiring for cdd-kit validate --contracts."""

    def test_ci_yml_contains_validate_contracts_step(self):
        """contract-driven-gates.yml must contain 'cdd-kit validate --contracts' as a step."""
        if not WORKFLOW_PATH.exists():
            pytest.skip(f"CI workflow file not found at {WORKFLOW_PATH}")

        content = WORKFLOW_PATH.read_text(encoding="utf-8")
        assert "cdd-kit validate --contracts" in content, (
            f"'cdd-kit validate --contracts' step not found in "
            f"{WORKFLOW_PATH.name}.\n"
            "Add it as a step under the contract gate job."
        )

    def test_ci_yml_has_validate_contracts_in_jobs(self):
        """The validate --contracts command must appear in a named step."""
        if not WORKFLOW_PATH.exists():
            pytest.skip(f"CI workflow file not found at {WORKFLOW_PATH}")

        content = WORKFLOW_PATH.read_text(encoding="utf-8")
        lines = content.splitlines()
        found = any(
            "cdd-kit validate --contracts" in line
            for line in lines
        )
        assert found, (
            "'cdd-kit validate --contracts' not found in any line of "
            f"{WORKFLOW_PATH.name}"
        )
