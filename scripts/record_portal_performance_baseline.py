#!/usr/bin/env python3
"""Record simple route latency baselines for legacy portal vs SPA shell."""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from mes_dashboard.app import create_app

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "migration" / "portal-no-iframe"


@dataclass
class RouteMetric:
    route: str
    samples_ms: list[float]
    status_codes: list[int]

    def to_dict(self) -> dict:
        sorted_samples = sorted(self.samples_ms)
        p95_idx = max(int(len(sorted_samples) * 0.95) - 1, 0)
        return {
            "route": self.route,
            "samples": len(self.samples_ms),
            "avg_ms": round(statistics.mean(self.samples_ms), 3),
            "p95_ms": round(sorted_samples[p95_idx], 3),
            "min_ms": round(min(self.samples_ms), 3),
            "max_ms": round(max(self.samples_ms), 3),
            "status_codes": sorted(set(self.status_codes)),
        }


def _measure_routes(routes: list[str], *, portal_spa_enabled: bool, samples: int = 15) -> dict:
    old = os.environ.get("PORTAL_SPA_ENABLED")
    os.environ["PORTAL_SPA_ENABLED"] = "true" if portal_spa_enabled else "false"
    try:
        app = create_app("testing")
        app.config["TESTING"] = True
        client = app.test_client()

        metrics: list[RouteMetric] = []
        for route in routes:
            sample_values: list[float] = []
            statuses: list[int] = []
            for _ in range(samples):
                started = time.perf_counter()
                response = client.get(route)
                elapsed_ms = (time.perf_counter() - started) * 1000
                sample_values.append(elapsed_ms)
                statuses.append(response.status_code)
            metrics.append(RouteMetric(route=route, samples_ms=sample_values, status_codes=statuses))

        return {
            "portal_spa_enabled": portal_spa_enabled,
            "samples_per_route": samples,
            "metrics": [metric.to_dict() for metric in metrics],
        }
    finally:
        if old is None:
            os.environ.pop("PORTAL_SPA_ENABLED", None)
        else:
            os.environ["PORTAL_SPA_ENABLED"] = old


def _build_comparison(legacy: dict, spa: dict) -> str:
    legacy_map = {item["route"]: item for item in legacy["metrics"]}
    spa_map = {item["route"]: item for item in spa["metrics"]}

    lines = [
        "# Performance Baseline Comparison",
        "",
        "Measured via Flask test client (route latency in ms).",
        "",
        "## Key Entry Routes",
        "",
        "| Surface | Avg (ms) | P95 (ms) |",
        "| --- | ---: | ---: |",
    ]

    legacy_entry = legacy_map.get("/")
    spa_entry = spa_map.get("/portal-shell")
    if legacy_entry:
        lines.append(f"| Legacy portal `/` | {legacy_entry['avg_ms']} | {legacy_entry['p95_ms']} |")
    if spa_entry:
        lines.append(f"| SPA shell `/portal-shell` | {spa_entry['avg_ms']} | {spa_entry['p95_ms']} |")

    lines.extend(
        [
            "",
            "## Shared API Route",
            "",
            "| Route | Legacy Avg (ms) | SPA Avg (ms) | Delta (ms) |",
            "| --- | ---: | ---: | ---: |",
        ]
    )

    shared_route = "/api/portal/navigation"
    old_item = legacy_map.get(shared_route)
    new_item = spa_map.get(shared_route)
    if old_item and new_item:
        delta = round(new_item["avg_ms"] - old_item["avg_ms"], 3)
        lines.append(
            f"| `{shared_route}` | {old_item['avg_ms']} | {new_item['avg_ms']} | {delta} |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This baseline is synthetic (test client), used for migration regression gate trend tracking.",
            "- Production browser/network RUM should be captured separately during canary rollout.",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    legacy_routes = [
        "/",
        "/api/portal/navigation",
        "/wip-overview",
        "/resource",
        "/qc-gate",
    ]
    spa_routes = [
        "/portal-shell",
        "/api/portal/navigation",
        "/job-query",
        "/excel-query",
        "/query-tool",
        "/tmtt-defect",
    ]

    legacy = _measure_routes(legacy_routes, portal_spa_enabled=False)
    spa = _measure_routes(spa_routes, portal_spa_enabled=True)

    legacy_path = OUT_DIR / "performance_baseline_legacy.json"
    spa_path = OUT_DIR / "performance_baseline_spa.json"
    compare_path = OUT_DIR / "performance_baseline_comparison.md"

    legacy_path.write_text(json.dumps(legacy, ensure_ascii=False, indent=2), encoding="utf-8")
    spa_path.write_text(json.dumps(spa, ensure_ascii=False, indent=2), encoding="utf-8")
    compare_path.write_text(_build_comparison(legacy, spa), encoding="utf-8")

    print(f"Wrote: {legacy_path}")
    print(f"Wrote: {spa_path}")
    print(f"Wrote: {compare_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
