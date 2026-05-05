# -*- coding: utf-8 -*-
"""Parity checks between backend formulas and frontend compute helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mes_dashboard.services.resource_history_service import (
    _calc_ou_pct,
    _calc_availability_pct,
    _calc_status_pct,
)


def _load_fixture() -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    fixture_path = repo_root / "tests" / "fixtures" / "frontend_compute_parity.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _backend_expected(case: dict[str, float]) -> dict[str, float]:
    prd = case['prd_hours']
    sby = case['sby_hours']
    udt = case['udt_hours']
    sdt = case['sdt_hours']
    egt = case['egt_hours']
    nst = case['nst_hours']
    total = prd + sby + udt + sdt + egt + nst

    return {
        'ou_pct': _calc_ou_pct(prd, sby, udt, sdt, egt),
        'availability_pct': _calc_availability_pct(prd, sby, udt, sdt, egt, nst),
        'prd_pct': _calc_status_pct(prd, total),
        'sby_pct': _calc_status_pct(sby, total),
        'udt_pct': _calc_status_pct(udt, total),
        'sdt_pct': _calc_status_pct(sdt, total),
        'egt_pct': _calc_status_pct(egt, total),
        'nst_pct': _calc_status_pct(nst, total),
    }


def test_frontend_compute_matches_backend_formulas():
    repo_root = Path(__file__).resolve().parents[1]
    compute_module = repo_root / 'frontend' / 'src' / 'core' / 'compute.ts'
    fixture = _load_fixture()
    cases = fixture["cases"]
    tolerance = fixture["metric_tolerance"]

    node_code = (
        "import { buildResourceKpiFromHours } from '" + compute_module.as_posix() + "';"
        "const cases = JSON.parse(process.argv[1]);"
        "const result = cases.map((c) => buildResourceKpiFromHours(c));"
        "console.log(JSON.stringify(result));"
    )

    completed = subprocess.run(
        ['node', '--experimental-strip-types', '--input-type=module', '-e', node_code, json.dumps(cases)],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    frontend_values = json.loads(completed.stdout)
    assert len(frontend_values) == len(cases)

    for idx, case in enumerate(cases):
        expected = _backend_expected(case)
        actual = frontend_values[idx]
        for key, value in expected.items():
            delta = abs(float(actual[key]) - float(value))
            assert delta <= float(tolerance.get(key, 0.0))
