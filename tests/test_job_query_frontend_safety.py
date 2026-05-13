# -*- coding: utf-8 -*-
"""Frontend safety contract tests for job-query module rendering."""

from __future__ import annotations

from pathlib import Path


def test_job_query_module_avoids_inline_onclick_string_interpolation():
    source = (
        Path(__file__).resolve().parents[1]
        / "frontend"
        / "src"
        / "job-query"
        / "main.ts"
    ).read_text(encoding="utf-8")

    assert "onclick=" not in source
    assert 'data-action="toggle-equipment"' in source
    assert 'data-action="toggle-job-history"' in source
    assert "encodeURIComponent(safeText(value))" in source
    assert "decodeURIComponent(value)" in source
