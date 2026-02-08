#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Benchmark cache query baseline vs indexed selection.

This benchmark is used as a repeatable governance harness for P1 cache/query
efficiency work. It focuses on deterministic synthetic workloads so operators
can compare relative latency and memory amplification over time.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "cache_benchmark_fixture.json"


def load_fixture(path: Path = FIXTURE_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if "rows" not in payload:
        raise ValueError("fixture requires rows")
    return payload


def build_dataset(rows: int, seed: int) -> pd.DataFrame:
    random.seed(seed)
    np.random.seed(seed)

    workcenters = [f"WC-{idx:02d}" for idx in range(1, 31)]
    packages = ["QFN", "DFN", "SOT", "SOP", "BGA", "TSOP"]
    types = ["TYPE-A", "TYPE-B", "TYPE-C", "TYPE-D"]
    statuses = ["RUN", "QUEUE", "HOLD"]
    hold_reasons = ["", "", "", "YieldLimit", "特殊需求管控", "PM Hold"]

    frame = pd.DataFrame(
        {
            "WORKCENTER_GROUP": np.random.choice(workcenters, rows),
            "PACKAGE_LEF": np.random.choice(packages, rows),
            "PJ_TYPE": np.random.choice(types, rows),
            "WIP_STATUS": np.random.choice(statuses, rows, p=[0.45, 0.35, 0.20]),
            "HOLDREASONNAME": np.random.choice(hold_reasons, rows),
            "QTY": np.random.randint(1, 500, rows),
            "WORKORDER": [f"WO-{i:06d}" for i in range(rows)],
            "LOTID": [f"LOT-{i:07d}" for i in range(rows)],
        }
    )
    return frame


def _build_index(df: pd.DataFrame) -> dict[str, dict[str, set[int]]]:
    def by_column(column: str) -> dict[str, set[int]]:
        grouped = df.groupby(column, dropna=True, sort=False).indices
        return {str(k): {int(i) for i in v} for k, v in grouped.items()}

    return {
        "workcenter": by_column("WORKCENTER_GROUP"),
        "package": by_column("PACKAGE_LEF"),
        "type": by_column("PJ_TYPE"),
        "status": by_column("WIP_STATUS"),
    }


def _baseline_query(df: pd.DataFrame, query: dict[str, str]) -> int:
    subset = df
    if query.get("workcenter"):
        subset = subset[subset["WORKCENTER_GROUP"] == query["workcenter"]]
    if query.get("package"):
        subset = subset[subset["PACKAGE_LEF"] == query["package"]]
    if query.get("type"):
        subset = subset[subset["PJ_TYPE"] == query["type"]]
    if query.get("status"):
        subset = subset[subset["WIP_STATUS"] == query["status"]]
    return int(len(subset))


def _indexed_query(_df: pd.DataFrame, indexes: dict[str, dict[str, set[int]]], query: dict[str, str]) -> int:
    selected: set[int] | None = None
    for key, bucket in (
        ("workcenter", "workcenter"),
        ("package", "package"),
        ("type", "type"),
        ("status", "status"),
    ):
        current = indexes[bucket].get(query.get(key, ""))
        if current is None:
            return 0
        if selected is None:
            selected = set(current)
        else:
            selected.intersection_update(current)
            if not selected:
                return 0
    return len(selected or ())


def _build_queries(df: pd.DataFrame, query_count: int, seed: int) -> list[dict[str, str]]:
    random.seed(seed + 17)
    workcenters = sorted(df["WORKCENTER_GROUP"].dropna().astype(str).unique().tolist())
    packages = sorted(df["PACKAGE_LEF"].dropna().astype(str).unique().tolist())
    types = sorted(df["PJ_TYPE"].dropna().astype(str).unique().tolist())
    statuses = sorted(df["WIP_STATUS"].dropna().astype(str).unique().tolist())

    queries: list[dict[str, str]] = []
    for _ in range(query_count):
        queries.append(
            {
                "workcenter": random.choice(workcenters),
                "package": random.choice(packages),
                "type": random.choice(types),
                "status": random.choice(statuses),
            }
        )
    return queries


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(max(math.ceil(0.95 * len(sorted_values)) - 1, 0), len(sorted_values) - 1)
    return sorted_values[index]


def run_benchmark(rows: int, query_count: int, seed: int) -> dict[str, Any]:
    df = build_dataset(rows=rows, seed=seed)
    queries = _build_queries(df, query_count=query_count, seed=seed)
    indexes = _build_index(df)

    baseline_latencies: list[float] = []
    indexed_latencies: list[float] = []
    baseline_rows: list[int] = []
    indexed_rows: list[int] = []

    for query in queries:
        start = time.perf_counter()
        baseline_rows.append(_baseline_query(df, query))
        baseline_latencies.append((time.perf_counter() - start) * 1000)

        start = time.perf_counter()
        indexed_rows.append(_indexed_query(df, indexes, query))
        indexed_latencies.append((time.perf_counter() - start) * 1000)

    if baseline_rows != indexed_rows:
        raise AssertionError("benchmark correctness drift: indexed result mismatch")

    frame_bytes = int(df.memory_usage(index=True, deep=True).sum())
    index_entries = sum(len(bucket) for buckets in indexes.values() for bucket in buckets.values())
    index_bytes_estimate = int(index_entries * 16)

    baseline_p95 = _p95(baseline_latencies)
    indexed_p95 = _p95(indexed_latencies)

    return {
        "rows": rows,
        "query_count": query_count,
        "seed": seed,
        "latency_ms": {
            "baseline_avg": round(statistics.fmean(baseline_latencies), 4),
            "baseline_p95": round(baseline_p95, 4),
            "indexed_avg": round(statistics.fmean(indexed_latencies), 4),
            "indexed_p95": round(indexed_p95, 4),
            "p95_ratio_indexed_vs_baseline": round(
                (indexed_p95 / baseline_p95) if baseline_p95 > 0 else 0.0,
                4,
            ),
        },
        "memory_bytes": {
            "frame": frame_bytes,
            "index_estimate": index_bytes_estimate,
            "amplification_ratio": round(
                (frame_bytes + index_bytes_estimate) / max(frame_bytes, 1),
                4,
            ),
        },
    }


def main() -> int:
    fixture = load_fixture()

    parser = argparse.ArgumentParser(description="Run cache baseline vs indexed benchmark")
    parser.add_argument("--rows", type=int, default=int(fixture.get("rows", 30000)))
    parser.add_argument("--queries", type=int, default=int(fixture.get("query_count", 400)))
    parser.add_argument("--seed", type=int, default=int(fixture.get("seed", 42)))
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    report = run_benchmark(rows=args.rows, query_count=args.queries, seed=args.seed)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not args.enforce:
        return 0

    thresholds = fixture.get("thresholds") or {}
    max_latency_ratio = float(thresholds.get("max_p95_ratio_indexed_vs_baseline", 1.25))
    max_amplification = float(thresholds.get("max_memory_amplification_ratio", 1.8))

    latency_ratio = float(report["latency_ms"]["p95_ratio_indexed_vs_baseline"])
    amplification_ratio = float(report["memory_bytes"]["amplification_ratio"])

    if latency_ratio > max_latency_ratio:
        raise SystemExit(
            f"Latency regression: {latency_ratio:.4f} > max allowed {max_latency_ratio:.4f}"
        )
    if amplification_ratio > max_amplification:
        raise SystemExit(
            f"Memory amplification regression: {amplification_ratio:.4f} > max allowed {max_amplification:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
