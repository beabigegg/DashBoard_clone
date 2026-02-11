#!/usr/bin/env python3
"""Generate baseline and contract-freeze artifacts for shell route-view migration."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mes_dashboard.services.navigation_contract import (
    compute_drawer_visibility,
    validate_drawer_page_contract,
    validate_route_migration_contract,
)


ROOT = Path(__file__).resolve().parent.parent
PAGE_STATUS_FILE = ROOT / "data" / "page_status.json"
OUT_DIR = ROOT / "docs" / "migration" / "portal-shell-route-view-integration"


TARGET_ROUTE_CONTRACTS: list[dict[str, Any]] = [
    {
        "route": "/wip-overview",
        "page_name": "WIP 即時概況",
        "render_mode": "native",
        "required_query_keys": ["workorder", "lotid", "package", "type", "status"],
        "source_dir": "frontend/src/wip-overview",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/wip-detail",
        "page_name": "WIP 詳細列表",
        "render_mode": "native",
        "required_query_keys": ["workcenter", "workorder", "lotid", "package", "type", "status"],
        "source_dir": "frontend/src/wip-detail",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/hold-overview",
        "page_name": "Hold 即時概況",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/hold-overview",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/hold-detail",
        "page_name": "Hold 詳細查詢",
        "render_mode": "native",
        "required_query_keys": ["reason"],
        "source_dir": "frontend/src/hold-detail",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/hold-history",
        "page_name": "Hold 歷史報表",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/hold-history",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/resource",
        "page_name": "設備即時狀況",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/resource-status",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/resource-history",
        "page_name": "設備歷史績效",
        "render_mode": "native",
        "required_query_keys": [
            "start_date",
            "end_date",
            "granularity",
            "workcenter_groups",
            "families",
            "resource_ids",
            "is_production",
            "is_key",
            "is_monitor",
        ],
        "source_dir": "frontend/src/resource-history",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/qc-gate",
        "page_name": "QC-GATE 狀態",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/qc-gate",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/job-query",
        "page_name": "設備維修查詢",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/job-query",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/excel-query",
        "page_name": "Excel 查詢工具",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/excel-query",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/query-tool",
        "page_name": "Query Tool",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/query-tool",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
    {
        "route": "/tmtt-defect",
        "page_name": "TMTT Defect",
        "render_mode": "native",
        "required_query_keys": [],
        "source_dir": "frontend/src/tmtt-defect",
        "owner": "frontend-mes-reporting",
        "rollback_strategy": "fallback_to_legacy_route",
    },
]


CRITICAL_API_PAYLOAD_CONTRACTS = {
    "/api/wip/overview/summary": {
        "required_keys": ["dataUpdateDate", "runLots", "queueLots", "holdLots"],
        "notes": "WIP summary cards",
    },
    "/api/wip/overview/matrix": {
        "required_keys": ["workcenters", "packages", "matrix", "workcenter_totals"],
        "notes": "WIP matrix table",
    },
    "/api/wip/hold-detail/summary": {
        "required_keys": ["workcenterCount", "packageCount", "lotCount"],
        "notes": "Hold detail KPI cards",
    },
    "/api/hold-overview/matrix": {
        "required_keys": ["rows", "totals"],
        "notes": "Hold overview matrix interaction",
    },
    "/api/hold-history/list": {
        "required_keys": ["rows", "summary"],
        "notes": "Hold history table and summary sync",
    },
    "/api/resource/status": {
        "required_keys": ["rows", "summary"],
        "notes": "Realtime resource status table",
    },
    "/api/resource/history/summary": {
        "required_keys": ["kpi", "trend", "heatmap", "workcenter_comparison"],
        "notes": "Resource history charts",
    },
    "/api/resource/history/detail": {
        "required_keys": ["data"],
        "notes": "Resource history detail table",
    },
    "/api/qc-gate/summary": {
        "required_keys": ["summary", "table", "pareto"],
        "notes": "QC-GATE chart/table linked view",
    },
    "/api/tmtt-defect/analysis": {
        "required_keys": ["kpi", "pareto", "trend", "detail"],
        "notes": "TMTT chart/table analysis payload",
    },
}


ROUTE_NOTES = {
    "/wip-overview": "filter URL sync + status drill-down to detail",
    "/wip-detail": "workcenter deep-link + list/detail continuity",
    "/hold-overview": "summary/matrix/lot interactions must remain stable",
    "/hold-detail": "requires reason; missing reason redirects",
    "/hold-history": "trend/pareto/duration/table interactions",
    "/resource": "status summary + table filtering semantics",
    "/resource-history": "date/granularity/group/family/resource/flags contract",
    "/qc-gate": "chart-table linked filtering parity",
    "/job-query": "resource/date query + txn detail + export",
    "/excel-query": "upload/detect/query/export workflow",
    "/query-tool": "resolve/history/associations/equipment-period workflows",
    "/tmtt-defect": "analysis + chart interactions + CSV export",
}


API_PATTERN = re.compile(r"[\"'`](/api/[A-Za-z0-9_./-]+)")


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _collect_source_files(source_dir: Path) -> list[Path]:
    if not source_dir.exists():
        return []
    files: list[Path] = []
    for path in source_dir.rglob("*"):
        if path.is_file() and path.suffix in {".vue", ".js", ".ts"}:
            files.append(path)
    return sorted(files)


def _collect_interaction_evidence(entry: dict[str, Any]) -> dict[str, Any]:
    source_dir = ROOT / str(entry["source_dir"])
    files = _collect_source_files(source_dir)
    rel_files = [str(path.relative_to(ROOT)) for path in files]

    chart_files: list[str] = []
    table_files: list[str] = []
    filter_files: list[str] = []
    matrix_files: list[str] = []
    sort_files: list[str] = []
    pagination_files: list[str] = []
    legend_files: list[str] = []
    tooltip_files: list[str] = []
    api_endpoints: set[str] = set()

    for path in files:
        rel = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8", errors="ignore")
        lower = text.lower()
        name_lower = path.name.lower()

        if "chart" in name_lower or "echarts" in lower or "vchart" in lower:
            chart_files.append(rel)
        if "table" in name_lower or "<table" in lower:
            table_files.append(rel)
        if "filter" in name_lower or "filter" in lower:
            filter_files.append(rel)
        if "matrix" in name_lower or "matrix" in lower:
            matrix_files.append(rel)
        if "sort" in lower:
            sort_files.append(rel)
        if "pagination" in lower or "page_size" in lower or "per_page" in lower:
            pagination_files.append(rel)
        if "legend" in lower:
            legend_files.append(rel)
        if "tooltip" in lower:
            tooltip_files.append(rel)

        for match in API_PATTERN.finditer(text):
            api_endpoints.add(match.group(1))

    return {
        "capture_method": "static_source_analysis",
        "source_dir": str(source_dir.relative_to(ROOT)),
        "source_files": rel_files,
        "table": {
            "component_files": sorted(set(table_files)),
            "has_sort_logic": bool(sort_files),
            "has_pagination": bool(pagination_files),
            "sort_hint_files": sorted(set(sort_files)),
            "pagination_hint_files": sorted(set(pagination_files)),
        },
        "chart": {
            "component_files": sorted(set(chart_files)),
            "has_legend_logic": bool(legend_files),
            "has_tooltip_logic": bool(tooltip_files),
            "legend_hint_files": sorted(set(legend_files)),
            "tooltip_hint_files": sorted(set(tooltip_files)),
        },
        "filter": {
            "required_query_keys": list(entry.get("required_query_keys", [])),
            "component_files": sorted(set(filter_files)),
        },
        "matrix": {
            "component_files": sorted(set(matrix_files)),
            "has_matrix_interaction": bool(matrix_files),
        },
        "api_endpoints": sorted(api_endpoints),
    }


def _build_route_query_contracts() -> dict[str, Any]:
    routes = {}
    for entry in TARGET_ROUTE_CONTRACTS:
        route = entry["route"]
        routes[route] = {
            "query_keys": entry["required_query_keys"],
            "render_mode": entry["render_mode"],
            "notes": ROUTE_NOTES.get(route, ""),
        }
    return {"generated_at": _iso_now(), "routes": routes}


def _build_route_contract_payload() -> dict[str, Any]:
    payload_routes: list[dict[str, Any]] = []
    for entry in TARGET_ROUTE_CONTRACTS:
        payload_routes.append(
            {
                "route_id": str(entry["route"]).strip("/").replace("/", "-") or "root",
                "route": entry["route"],
                "page_name": entry["page_name"],
                "render_mode": entry["render_mode"],
                "required_query_keys": entry["required_query_keys"],
                "owner": entry["owner"],
                "rollback_strategy": entry["rollback_strategy"],
                "source_dir": entry["source_dir"],
            }
        )

    return {
        "generated_at": _iso_now(),
        "description": "Route-level migration contract freeze for shell route-view integration.",
        "routes": payload_routes,
    }


def _render_route_parity_matrix_markdown(
    route_contract: dict[str, Any],
    evidence_by_route: dict[str, Any],
) -> str:
    lines = [
        "# Route Parity Matrix (Shell Route-View Integration)",
        "",
        f"Generated at: `{route_contract['generated_at']}`",
        "",
        "| Route | Mode | Required Query Keys | Table / Filter Focus | Chart / Matrix Focus | Owner | Rollback |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for item in route_contract["routes"]:
        route = item["route"]
        evidence = evidence_by_route.get(route, {})
        table = evidence.get("table", {})
        chart = evidence.get("chart", {})
        matrix = evidence.get("matrix", {})

        query_keys = ", ".join(item.get("required_query_keys", [])) or "-"
        table_focus = (
            f"table_files={len(table.get('component_files', []))}; "
            f"sort={'Y' if table.get('has_sort_logic') else 'N'}; "
            f"pagination={'Y' if table.get('has_pagination') else 'N'}"
        )
        chart_focus = (
            f"chart_files={len(chart.get('component_files', []))}; "
            f"legend={'Y' if chart.get('has_legend_logic') else 'N'}; "
            f"tooltip={'Y' if chart.get('has_tooltip_logic') else 'N'}; "
            f"matrix={'Y' if matrix.get('has_matrix_interaction') else 'N'}"
        )
        lines.append(
            f"| `{route}` | `{item['render_mode']}` | `{query_keys}` | "
            f"{table_focus} | {chart_focus} | `{item['owner']}` | `{item['rollback_strategy']}` |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Matrix and chart/table links are validated further in per-page smoke and parity tests.",
            "- All target routes are in native mode; no iframe/wrapper runtime host remains in shell content path.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_contract_markdown(route_contract: dict[str, Any]) -> str:
    lines = [
        "# Route Migration Contract Freeze",
        "",
        f"Generated at: `{route_contract['generated_at']}`",
        "",
        "This contract freezes route ownership and migration mode for shell cutover governance.",
        "",
        "| Route ID | Route | Mode | Required Query Keys | Owner | Rollback Strategy |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in route_contract["routes"]:
        query_keys = ", ".join(item.get("required_query_keys", [])) or "-"
        lines.append(
            f"| `{item['route_id']}` | `{item['route']}` | `{item['render_mode']}` | "
            f"`{query_keys}` | `{item['owner']}` | `{item['rollback_strategy']}` |"
        )

    lines.extend(
        [
            "",
            "## Validation Rules",
            "",
            "- Missing route definitions are treated as blocking contract errors.",
            "- Duplicate route definitions are rejected.",
            "- `render_mode` MUST be `native` or `wrapper`.",
            "- `owner` and `rollback_strategy` MUST be non-empty.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.loads(PAGE_STATUS_FILE.read_text(encoding="utf-8"))

    visibility = {
        "generated_at": _iso_now(),
        "source": str(PAGE_STATUS_FILE.relative_to(ROOT)),
        "admin": compute_drawer_visibility(raw, is_admin=True),
        "non_admin": compute_drawer_visibility(raw, is_admin=False),
    }
    write_json(OUT_DIR / "baseline_drawer_visibility.json", visibility)

    drawer_validation = {
        "generated_at": _iso_now(),
        "source": str(PAGE_STATUS_FILE.relative_to(ROOT)),
        "errors": validate_drawer_page_contract(raw),
    }
    write_json(OUT_DIR / "baseline_drawer_contract_validation.json", drawer_validation)

    route_query_contracts = _build_route_query_contracts()
    write_json(OUT_DIR / "baseline_route_query_contracts.json", route_query_contracts)

    payload_contracts = {
        "generated_at": _iso_now(),
        "source": "frontend API contracts observed in report modules",
        "apis": CRITICAL_API_PAYLOAD_CONTRACTS,
    }
    write_json(OUT_DIR / "baseline_api_payload_contracts.json", payload_contracts)

    route_contract = _build_route_contract_payload()
    write_json(OUT_DIR / "route_migration_contract.json", route_contract)

    required_routes = {str(item["route"]) for item in TARGET_ROUTE_CONTRACTS}
    contract_errors = validate_route_migration_contract(route_contract, required_routes=required_routes)
    contract_validation = {
        "generated_at": _iso_now(),
        "errors": contract_errors,
    }
    write_json(OUT_DIR / "route_migration_contract_validation.json", contract_validation)

    evidence_by_route = {
        str(item["route"]): _collect_interaction_evidence(item)
        for item in TARGET_ROUTE_CONTRACTS
    }
    interaction_evidence = {
        "generated_at": _iso_now(),
        "capture_scope": [str(item["route"]) for item in TARGET_ROUTE_CONTRACTS],
        "routes": evidence_by_route,
    }
    write_json(OUT_DIR / "baseline_interaction_evidence.json", interaction_evidence)

    (OUT_DIR / "route_parity_matrix.md").write_text(
        _render_route_parity_matrix_markdown(route_contract, evidence_by_route),
        encoding="utf-8",
    )
    (OUT_DIR / "route_migration_contract.md").write_text(
        _render_contract_markdown(route_contract),
        encoding="utf-8",
    )

    if contract_errors:
        raise SystemExit(
            "Generated artifacts, but route migration contract has errors: "
            + "; ".join(contract_errors)
        )

    print("Generated shell route-view baseline artifacts under", OUT_DIR)


if __name__ == "__main__":
    main()
