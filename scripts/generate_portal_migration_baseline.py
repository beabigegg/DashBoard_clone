#!/usr/bin/env python3
"""Generate baseline snapshots for portal no-iframe migration."""

from __future__ import annotations

import json
from pathlib import Path

from mes_dashboard.services.navigation_contract import (
    compute_drawer_visibility,
    validate_drawer_page_contract,
)


ROOT = Path(__file__).resolve().parent.parent
PAGE_STATUS_FILE = ROOT / "data" / "page_status.json"
OUT_DIR = ROOT / "docs" / "migration" / "portal-no-iframe"


ROUTE_QUERY_CONTRACTS = {
    "/wip-overview": {
        "query_keys": ["workorder", "lotid", "package", "type", "status"],
        "notes": "filters + status URL state must remain compatible",
    },
    "/wip-detail": {
        "query_keys": ["workcenter", "workorder", "lotid", "package", "type", "status"],
        "notes": "workcenter deep-link and back-link query continuity",
    },
    "/hold-detail": {
        "query_keys": ["reason"],
        "notes": "reason required for normal access flow",
    },
    "/resource-history": {
        "query_keys": [
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
        "notes": "query/export params must remain compatible",
    },
}


CRITICAL_API_PAYLOAD_CONTRACTS = {
    "/api/wip/overview/summary": {
        "required_keys": ["dataUpdateDate", "runLots", "queueLots", "holdLots"],
        "notes": "summary header and cards depend on these fields",
    },
    "/api/wip/overview/matrix": {
        "required_keys": ["workcenters", "packages", "matrix", "workcenter_totals"],
        "notes": "matrix table rendering contract",
    },
    "/api/wip/hold-detail/summary": {
        "required_keys": ["workcenterCount", "packageCount", "lotCount"],
        "notes": "hold detail summary cards contract",
    },
    "/api/resource/history/summary": {
        "required_keys": ["kpi", "trend", "heatmap", "workcenter_comparison"],
        "notes": "resource history chart summary contract",
    },
    "/api/resource/history/detail": {
        "required_keys": ["data"],
        "notes": "detail table contract (plus truncated/max_records metadata when present)",
    },
}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.loads(PAGE_STATUS_FILE.read_text(encoding="utf-8"))

    visibility = {
        "source": str(PAGE_STATUS_FILE.relative_to(ROOT)),
        "admin": compute_drawer_visibility(raw, is_admin=True),
        "non_admin": compute_drawer_visibility(raw, is_admin=False),
    }
    write_json(OUT_DIR / "baseline_drawer_visibility.json", visibility)

    route_contracts = {
        "source": "frontend route parsing and current parity matrix",
        "routes": ROUTE_QUERY_CONTRACTS,
    }
    write_json(OUT_DIR / "baseline_route_query_contracts.json", route_contracts)

    payload_contracts = {
        "source": "current frontend API consumption contracts",
        "apis": CRITICAL_API_PAYLOAD_CONTRACTS,
    }
    write_json(OUT_DIR / "baseline_api_payload_contracts.json", payload_contracts)

    validation = {
        "source": str(PAGE_STATUS_FILE.relative_to(ROOT)),
        "errors": validate_drawer_page_contract(raw),
    }
    write_json(OUT_DIR / "baseline_drawer_contract_validation.json", validation)

    print("Generated baseline snapshots under", OUT_DIR)


if __name__ == "__main__":
    main()
