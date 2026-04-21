#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stability measurement runner for real-infra integration tests.

Each invocation runs one or more pytest targets N times and appends
structured results to stability-results.jsonl in the project root.

Usage:
    python scripts/measure_real_infra_stability.py \\
        --tests multi_worker,redis_chaos,real_multi_worker \\
        --runs 3

    python scripts/measure_real_infra_stability.py \\
        --tests multi_worker \\
        --runs 1 \\
        --out /tmp/stability-results.jsonl

The JSONL schema is stable across versions:
    {
        "date":      "2026-04-21T02:30:00Z",   # ISO-8601 UTC
        "test":      "multi_worker",              # logical test group name
        "run":       1,                         # 1-based within this invocation
        "passed":    true,                      # overall pass/fail
        "duration":  12.34,                     # wall-clock seconds
        "tests_run": 8,
        "tests_failed": 0,
        "retries":   0                          # future: pytest-rerun-failures
    }

Summary printed to stdout at end of each invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Known test targets
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_TARGET_PATHS: Dict[str, str] = {
    "multi_worker":      "tests/integration/test_multi_worker_concurrency.py",
    "redis_chaos":       "tests/integration/test_redis_chaos.py",
    "real_multi_worker": "tests/integration/test_real_multi_worker.py",
    "oracle_smoke":      "tests/integration/test_real_oracle_fault_injection.py",
    "redis_timeout":     "tests/integration/test_redis_timeout_fallback.py",
    "race_conditions":   "tests/integration/test_race_conditions.py",
}

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _resolve_targets(names: List[str]) -> List[tuple[str, str]]:
    """Return [(logical_name, pytest_path), ...], validating each name."""
    result = []
    for name in names:
        if name not in _TARGET_PATHS:
            known = ", ".join(sorted(_TARGET_PATHS))
            print(f"ERROR: unknown target {name!r}. Known targets: {known}", file=sys.stderr)
            sys.exit(1)
        result.append((name, _TARGET_PATHS[name]))
    return result


def _run_once(target_path: str, json_out: Path) -> dict:
    """Run pytest once against target_path.  Returns a partial result dict."""
    cmd = [
        sys.executable, "-m", "pytest",
        target_path,
        "--run-integration-real",
        "--tb=line",
        "-q",
        f"--json-report",
        f"--json-report-file={json_out}",
    ]

    start = time.monotonic()
    proc = subprocess.run(
        cmd,
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    duration = time.monotonic() - start

    passed = proc.returncode == 0
    tests_run = 0
    tests_failed = 0

    if json_out.exists():
        try:
            report = json.loads(json_out.read_text())
            summary = report.get("summary", {})
            tests_run = summary.get("total", 0)
            tests_failed = summary.get("failed", 0) + summary.get("error", 0)
        except Exception:
            pass

    return {
        "passed": passed,
        "duration": round(duration, 3),
        "tests_run": tests_run,
        "tests_failed": tests_failed,
        "retries": 0,
    }


def _append_record(out_path: Path, record: dict) -> None:
    with out_path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def _print_summary(results: List[dict]) -> None:
    if not results:
        return

    tests = sorted({r["test"] for r in results})
    print("\n" + "=" * 60)
    print("Stability measurement summary")
    print("=" * 60)
    for test in tests:
        runs = [r for r in results if r["test"] == test]
        n = len(runs)
        n_pass = sum(1 for r in runs if r["passed"])
        durations = [r["duration"] for r in runs]
        mean_d = sum(durations) / n
        p95_d = sorted(durations)[max(0, int(n * 0.95) - 1)]
        print(f"\n  {test}")
        print(f"    runs:      {n}")
        print(f"    pass rate: {n_pass}/{n} = {100*n_pass/n:.1f}%")
        print(f"    mean wall: {mean_d:.1f}s")
        print(f"    p95 wall:  {p95_d:.1f}s")
    print("=" * 60 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real-infra tests repeatedly and record stability metrics."
    )
    parser.add_argument(
        "--tests",
        required=True,
        help="Comma-separated list of test targets (e.g. multi_worker,redis_chaos)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of consecutive runs per target (default: 1)",
    )
    parser.add_argument(
        "--out",
        default=str(_PROJECT_ROOT / "stability-results.jsonl"),
        help="Path to the JSONL output file (appended, not overwritten)",
    )
    args = parser.parse_args()

    target_names = [t.strip() for t in args.tests.split(",") if t.strip()]
    targets = _resolve_targets(target_names)
    out_path = Path(args.out)

    all_records: List[dict] = []

    for logical_name, path in targets:
        for run_num in range(1, args.runs + 1):
            print(f"[{logical_name}] run {run_num}/{args.runs} ...", end="", flush=True)
            tmp_json = Path(os.environ.get("TMPDIR", "/tmp")) / f"stability-{logical_name}-{run_num}.json"

            partial = _run_once(path, tmp_json)
            status = "PASS" if partial["passed"] else "FAIL"
            print(f" {status} ({partial['duration']:.1f}s, {partial['tests_run']} tests)")

            record: dict = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "test": logical_name,
                "run": run_num,
                **partial,
            }
            _append_record(out_path, record)
            all_records.append(record)

            if tmp_json.exists():
                tmp_json.unlink(missing_ok=True)

    _print_summary(all_records)

    any_failed = any(not r["passed"] for r in all_records)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
