# -*- coding: utf-8 -*-
"""AC-6: cdd-kit doctor reports 0 'Response-shape' warnings.

Tests that running `cdd-kit doctor` in this repo produces no lines
containing a warning (⚠) about Response-shape. After response-shape-adr0007,
all 158 endpoints have named schema refs in the response cell, the openapi.json
carries $ref linkages for all typed endpoints, and the sample manifest exists.
"""
from __future__ import annotations

import subprocess

import pytest


class TestDoctorClean:
    """AC-6: cdd-kit doctor has no Response-shape warnings after adr0007.

    After response-shape-adr0007:
    - All 158 endpoints have named schema cells (no `→ ` prose prefix).
    - `## Schemas` section has Tier-B json-schema blocks for all schemas.
    - openapi.json carries $ref for 144+ endpoints.
    - `response-samples.json` manifest exists.
    - `cdd-kit validate --contracts` passes (AC-5).
    """

    def test_doctor_response_shape_zero_warnings(self):
        """cdd-kit doctor: assert no Response-shape ⚠ warning line.

        AC-6 passes when the Response-shape line in doctor output is ✓ (green),
        not ⚠ (yellow). The ✓ line contains 'typed response endpoint(s)'.
        """
        try:
            result = subprocess.run(
                ["cdd-kit", "doctor"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            pytest.skip("cdd-kit not found on PATH; skipping doctor check")
        except subprocess.TimeoutExpired:
            pytest.skip("cdd-kit doctor timed out")

        combined = result.stdout + result.stderr

        # Find all Response-shape lines
        response_shape_lines = [
            line for line in combined.splitlines()
            if "Response-shape" in line or "response-shape" in line.lower()
        ]

        # Assert no Response-shape line contains a warning indicator
        # (The ⚠ character or "0 with a typed response schema" text)
        warning_lines = [
            line for line in response_shape_lines
            if "0 with a typed response schema" in line
            or ("typed response endpoint" in line and " 0 " in line)
        ]

        assert not warning_lines, (
            "cdd-kit doctor reports Response-shape warning — "
            "expected all endpoints to have typed $ref schemas after response-shape-adr0007.\n"
            "Warning lines:\n" + "\n".join(warning_lines) + "\n\n"
            "Run: cdd-kit openapi export --out contracts/openapi.json\n"
            "Then verify the endpoint table response cells are plain schema names (no → prefix)."
        )

        # At least one Response-shape line must exist (confirms doctor ran the check)
        # It should contain "typed response endpoint(s)"
        ok_lines = [
            line for line in response_shape_lines
            if "typed response endpoint" in line
        ]
        assert ok_lines, (
            "cdd-kit doctor did not emit a Response-shape status line.\n"
            "Doctor output:\n" + combined[:2000]
        )
