# -*- coding: utf-8 -*-
"""SQL Optimization Parity Verification Script.

Connects to Oracle, runs original vs optimized SQL side-by-side,
compares results for data parity, captures EXPLAIN PLAN costs,
and produces a structured report.

Usage:
    conda activate mes-dashboard
    python scripts/sql_optimization_verify.py --all
    python scripts/sql_optimization_verify.py --severity CRITICAL
    python scripts/sql_optimization_verify.py --module hold_history
    python scripts/sql_optimization_verify.py --dry-run
    python scripts/sql_optimization_verify.py --all --output reports/sql_opt_report.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Bootstrap: load .env before importing project modules ────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

import pandas as pd
from sqlalchemy import create_engine, text

from mes_dashboard.config.database import CONNECTION_STRING
from mes_dashboard.sql import SQLLoader
from mes_dashboard.sql.filters import CommonFilters

logger = logging.getLogger("sql_optimization_verify")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class TestCase:
    """Defines one original-vs-optimized SQL comparison."""

    name: str
    severity: str  # CRITICAL / HIGH / MEDIUM / LOW
    module: str  # hold_history, dashboard, resource, etc.
    original: str  # SQL file name (without .sql)
    optimized: str  # SQL file name (without .sql)
    params: Dict[str, Any] = field(default_factory=dict)
    placeholders: Dict[str, str] = field(default_factory=dict)
    sort_columns: List[str] = field(default_factory=list)
    float_tolerance: float = 0.01
    ignore_columns: List[str] = field(default_factory=list)
    description: str = ""
    impact: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParityResult:
    """Result of one parity comparison."""

    name: str
    severity: str
    module: str
    status: str  # PASS / FAIL / ERROR / SKIP
    row_count_match: bool = False
    column_match: bool = False
    data_match: bool = False
    orig_rows: int = 0
    opt_rows: int = 0
    orig_cost: Optional[float] = None
    opt_cost: Optional[float] = None
    cost_reduction_pct: Optional[float] = None
    orig_elapsed_ms: float = 0.0
    opt_elapsed_ms: float = 0.0
    speedup_ratio: float = 0.0
    mismatches: List[str] = field(default_factory=list)
    error_message: str = ""
    description: str = ""
    impact: Dict[str, Any] = field(default_factory=dict)


# ── SQL Parity Verifier ─────────────────────────────────────────────────────


class SQLParityVerifier:
    """Runs original and optimized SQL, compares results and EXPLAIN PLAN."""

    def __init__(self, connection_string: str):
        self.engine = create_engine(
            connection_string,
            pool_size=2,
            max_overflow=0,
            pool_timeout=30,
            pool_recycle=300,
        )

    def close(self):
        self.engine.dispose()

    def _load_sql(self, name: str, placeholders: Dict[str, str]) -> str:
        """Load SQL file and apply structural placeholders."""
        sql = SQLLoader.load(name)
        for key, value in placeholders.items():
            sql = sql.replace(f"{{{{ {key} }}}}", value)
        return sql

    def _run_and_time(
        self, sql: str, params: Dict[str, Any], label: str = ""
    ) -> Tuple[pd.DataFrame, float]:
        """Execute SQL and return (DataFrame, elapsed_ms)."""
        start = time.perf_counter()
        with self.engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
            df.columns = [c.upper() for c in df.columns]
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(f"  {label}: {len(df)} rows in {elapsed:.0f}ms")
        return df, elapsed

    def _get_explain_cost(
        self, sql: str, params: Dict[str, Any]
    ) -> Optional[float]:
        """Run EXPLAIN PLAN and extract total cost."""
        try:
            stmt_id = f"opt_{int(time.time() * 1000) % 1_000_000}"
            explain_sql = f"EXPLAIN PLAN SET STATEMENT_ID = '{stmt_id}' FOR {sql}"
            with self.engine.connect() as conn:
                conn.execute(text(explain_sql), params)
                plan_rows = conn.execute(
                    text(
                        "SELECT COST FROM PLAN_TABLE "
                        "WHERE STATEMENT_ID = :sid AND ID = 0"
                    ),
                    {"sid": stmt_id},
                ).fetchone()
                # Clean up
                conn.execute(
                    text("DELETE FROM PLAN_TABLE WHERE STATEMENT_ID = :sid"),
                    {"sid": stmt_id},
                )
                conn.commit()
                if plan_rows and plan_rows[0] is not None:
                    return float(plan_rows[0])
        except Exception as e:
            logger.warning(f"  EXPLAIN PLAN failed: {e}")
        return None

    def _compare(
        self,
        df_orig: pd.DataFrame,
        df_opt: pd.DataFrame,
        sort_columns: List[str],
        float_tolerance: float,
        ignore_columns: List[str],
    ) -> Tuple[bool, bool, bool, List[str]]:
        """Compare two DataFrames.

        Returns: (row_count_match, column_match, data_match, mismatches)
        """
        mismatches: List[str] = []

        # Column comparison
        orig_cols = set(df_orig.columns)
        opt_cols = set(df_opt.columns)
        ignore_set = {c.upper() for c in ignore_columns}
        orig_cols -= ignore_set
        opt_cols -= ignore_set

        column_match = orig_cols == opt_cols
        if not column_match:
            missing = orig_cols - opt_cols
            extra = opt_cols - orig_cols
            if missing:
                mismatches.append(f"Missing columns in optimized: {missing}")
            if extra:
                mismatches.append(f"Extra columns in optimized: {extra}")

        # Row count
        row_count_match = len(df_orig) == len(df_opt)
        if not row_count_match:
            mismatches.append(
                f"Row count: original={len(df_orig)}, optimized={len(df_opt)}"
            )

        # Data comparison (only if columns match and row counts match)
        data_match = False
        if column_match and row_count_match and len(df_orig) > 0:
            compare_cols = sorted(orig_cols & opt_cols)
            df_o = df_orig[compare_cols].copy()
            df_n = df_opt[compare_cols].copy()

            # Sort if sort columns provided
            valid_sort = [c for c in sort_columns if c in compare_cols]
            if valid_sort:
                df_o = df_o.sort_values(valid_sort).reset_index(drop=True)
                df_n = df_n.sort_values(valid_sort).reset_index(drop=True)
            else:
                df_o = df_o.reset_index(drop=True)
                df_n = df_n.reset_index(drop=True)

            # Cell-by-cell comparison
            diff_count = 0
            for col in compare_cols:
                for idx in range(len(df_o)):
                    v_orig = df_o.at[idx, col]
                    v_opt = df_n.at[idx, col]

                    # Both null
                    if pd.isna(v_orig) and pd.isna(v_opt):
                        continue
                    # One null
                    if pd.isna(v_orig) or pd.isna(v_opt):
                        diff_count += 1
                        if len(mismatches) < 10:
                            mismatches.append(
                                f"Row {idx}, col {col}: "
                                f"orig={v_orig}, opt={v_opt}"
                            )
                        continue
                    # Float comparison
                    if isinstance(v_orig, float) or isinstance(v_opt, float):
                        try:
                            if abs(float(v_orig) - float(v_opt)) > float_tolerance:
                                diff_count += 1
                                if len(mismatches) < 10:
                                    mismatches.append(
                                        f"Row {idx}, col {col}: "
                                        f"orig={v_orig}, opt={v_opt} "
                                        f"(diff={abs(float(v_orig)-float(v_opt)):.6f})"
                                    )
                        except (ValueError, TypeError):
                            if str(v_orig) != str(v_opt):
                                diff_count += 1
                                if len(mismatches) < 10:
                                    mismatches.append(
                                        f"Row {idx}, col {col}: "
                                        f"orig={v_orig}, opt={v_opt}"
                                    )
                        continue
                    # General comparison
                    if str(v_orig) != str(v_opt):
                        diff_count += 1
                        if len(mismatches) < 10:
                            mismatches.append(
                                f"Row {idx}, col {col}: "
                                f"orig={v_orig}, opt={v_opt}"
                            )

            data_match = diff_count == 0
            if diff_count > 0:
                mismatches.append(f"Total cell differences: {diff_count}")
        elif column_match and row_count_match and len(df_orig) == 0:
            data_match = True  # Both empty

        return row_count_match, column_match, data_match, mismatches

    def verify_pair(self, tc: TestCase) -> ParityResult:
        """Run one original-vs-optimized comparison."""
        result = ParityResult(
            name=tc.name,
            severity=tc.severity,
            module=tc.module,
            status="ERROR",
            description=tc.description,
            impact=tc.impact,
        )

        try:
            # Load SQL
            orig_sql = self._load_sql(tc.original, tc.placeholders)
            opt_sql = self._load_sql(tc.optimized, tc.placeholders)

            logger.info(f"\n{'='*60}")
            logger.info(f"Testing: {tc.name}")
            logger.info(f"  Severity: {tc.severity} | Module: {tc.module}")

            # Execute both
            df_orig, t_orig = self._run_and_time(orig_sql, tc.params, "Original")
            df_opt, t_opt = self._run_and_time(opt_sql, tc.params, "Optimized")

            result.orig_rows = len(df_orig)
            result.opt_rows = len(df_opt)
            result.orig_elapsed_ms = round(t_orig, 1)
            result.opt_elapsed_ms = round(t_opt, 1)
            result.speedup_ratio = (
                round(t_orig / t_opt, 2) if t_opt > 0 else 0.0
            )

            # EXPLAIN PLAN
            logger.info("  Running EXPLAIN PLAN...")
            result.orig_cost = self._get_explain_cost(orig_sql, tc.params)
            result.opt_cost = self._get_explain_cost(opt_sql, tc.params)
            if result.orig_cost and result.opt_cost and result.orig_cost > 0:
                result.cost_reduction_pct = round(
                    (1 - result.opt_cost / result.orig_cost) * 100, 1
                )
            logger.info(
                f"  Cost: {result.orig_cost} → {result.opt_cost} "
                f"({result.cost_reduction_pct}%)"
            )

            # Compare data
            (
                result.row_count_match,
                result.column_match,
                result.data_match,
                result.mismatches,
            ) = self._compare(
                df_orig,
                df_opt,
                tc.sort_columns,
                tc.float_tolerance,
                tc.ignore_columns,
            )

            if result.row_count_match and result.column_match and result.data_match:
                result.status = "PASS"
                logger.info(f"  Result: PASS (speedup {result.speedup_ratio}x)")
            else:
                result.status = "FAIL"
                logger.warning(f"  Result: FAIL")
                for m in result.mismatches[:5]:
                    logger.warning(f"    {m}")

        except FileNotFoundError as e:
            result.status = "SKIP"
            result.error_message = str(e)
            logger.warning(f"  SKIP: {e}")
        except Exception as e:
            result.status = "ERROR"
            result.error_message = str(e)
            logger.error(f"  ERROR: {e}")

        return result


# ── Report Generation ────────────────────────────────────────────────────────


def _generate_console_report(results: List[ParityResult]) -> str:
    """Generate human-readable table for console output."""
    lines = []
    lines.append("")
    lines.append("=" * 100)
    lines.append(f"  SQL Optimization Verification Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 100)
    lines.append("")

    header = f" {'#':>2} | {'Severity':<8} | {'SQL File':<40} | {'Status':<6} | {'Rows':<8} | {'Cost Δ':<8} | {'Time Δ':<8} | {'Schema':<6}"
    sep = "-" * len(header)
    lines.append(header)
    lines.append(sep)

    for i, r in enumerate(results, 1):
        rows_str = (
            f"={r.orig_rows}" if r.row_count_match else f"{r.orig_rows}→{r.opt_rows}"
        )
        cost_str = f"{r.cost_reduction_pct}%" if r.cost_reduction_pct is not None else "N/A"
        time_str = f"{r.speedup_ratio}x" if r.speedup_ratio > 0 else "N/A"
        schema_str = "same" if r.column_match else "DIFF"
        lines.append(
            f" {i:>2} | {r.severity:<8} | {r.name:<40} | {r.status:<6} | {rows_str:<8} | {cost_str:<8} | {time_str:<8} | {schema_str:<6}"
        )

    lines.append(sep)

    # Summary
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")
    skipped = sum(1 for r in results if r.status == "SKIP")
    total = len(results)

    cost_reductions = [
        r.cost_reduction_pct for r in results if r.cost_reduction_pct is not None
    ]
    avg_cost = (
        round(sum(cost_reductions) / len(cost_reductions), 1)
        if cost_reductions
        else 0
    )

    speedups = [r.speedup_ratio for r in results if r.speedup_ratio > 0]
    avg_speedup = (
        round(sum(speedups) / len(speedups), 1) if speedups else 0
    )

    lines.append("")
    lines.append(
        f"  SUMMARY: {passed}/{total} passed, {failed} failed, "
        f"{errors} errors, {skipped} skipped"
    )
    lines.append(f"  Average cost reduction: {avg_cost}%")
    lines.append(f"  Average speedup: {avg_speedup}x")
    lines.append("")

    return "\n".join(lines)


def _generate_json_report(
    results: List[ParityResult], test_cases: List[TestCase]
) -> Dict[str, Any]:
    """Generate structured JSON report."""
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    errors = sum(1 for r in results if r.status == "ERROR")
    skipped = sum(1 for r in results if r.status == "SKIP")

    cost_reductions = [
        r.cost_reduction_pct for r in results if r.cost_reduction_pct is not None
    ]
    speedups = [r.speedup_ratio for r in results if r.speedup_ratio > 0]

    return {
        "report_date": datetime.now().isoformat(),
        "database": "Oracle (DWH)",
        "total_tests": len(results),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "summary": {
            "total_cost_reduction_pct": (
                round(sum(cost_reductions) / len(cost_reductions), 1)
                if cost_reductions
                else None
            ),
            "avg_speedup_ratio": (
                round(sum(speedups) / len(speedups), 1) if speedups else None
            ),
            "critical_tested": sum(
                1 for r in results if r.severity == "CRITICAL"
            ),
            "high_tested": sum(1 for r in results if r.severity == "HIGH"),
            "medium_tested": sum(
                1 for r in results if r.severity == "MEDIUM"
            ),
        },
        "results": [asdict(r) for r in results],
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="SQL Optimization Parity Verification"
    )
    parser.add_argument(
        "--all", action="store_true", help="Run all test cases"
    )
    parser.add_argument(
        "--severity",
        choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        help="Filter by severity",
    )
    parser.add_argument("--module", help="Filter by module name")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List test cases without executing",
    )
    parser.add_argument(
        "--output", help="Output JSON report to file path"
    )
    parser.add_argument(
        "--name", help="Run a single test case by name substring"
    )
    args = parser.parse_args()

    # Import test cases
    from sql_opt_test_cases import get_test_cases

    test_cases = get_test_cases()

    # Filter
    if args.severity:
        test_cases = [tc for tc in test_cases if tc.severity == args.severity]
    if args.module:
        test_cases = [tc for tc in test_cases if tc.module == args.module]
    if args.name:
        test_cases = [
            tc for tc in test_cases if args.name.lower() in tc.name.lower()
        ]
    if not args.all and not args.severity and not args.module and not args.name:
        parser.print_help()
        sys.exit(0)

    if args.dry_run:
        print(f"\nTest cases ({len(test_cases)}):\n")
        for i, tc in enumerate(test_cases, 1):
            print(
                f"  {i:>2}. [{tc.severity:<8}] {tc.name:<45} "
                f"({tc.original} → {tc.optimized})"
            )
        print()
        sys.exit(0)

    if not test_cases:
        print("No test cases match the filter criteria.")
        sys.exit(1)

    # Run verification
    verifier = SQLParityVerifier(CONNECTION_STRING)
    results: List[ParityResult] = []

    try:
        for tc in test_cases:
            result = verifier.verify_pair(tc)
            results.append(result)
    finally:
        verifier.close()

    # Console report
    console_report = _generate_console_report(results)
    print(console_report)

    # JSON report
    if args.output:
        report = _generate_json_report(results, test_cases)
        output_path = _PROJECT_ROOT / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)
        print(f"  JSON report saved to: {output_path}")


if __name__ == "__main__":
    main()
