#!/usr/bin/env python3
"""Run governance/quality/readiness checks for full modernization change."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs" / "migration" / "full-modernization-architecture-blueprint"
SCOPE_MATRIX_FILE = DOCS_DIR / "route_scope_matrix.json"
ROUTE_CONTRACT_FILE = DOCS_DIR / "route_contracts.json"
EXCEPTION_REGISTRY_FILE = DOCS_DIR / "exception_registry.json"
QUALITY_POLICY_FILE = DOCS_DIR / "quality_gate_policy.json"
ASSET_MANIFEST_FILE = DOCS_DIR / "asset_readiness_manifest.json"
KNOWN_BUG_BASELINE_FILE = DOCS_DIR / "known_bug_baseline.json"
MANUAL_ACCEPTANCE_FILE = DOCS_DIR / "manual_acceptance_records.json"
BUG_REVALIDATION_FILE = DOCS_DIR / "bug_revalidation_records.json"
STYLE_INVENTORY_FILE = DOCS_DIR / "style_inventory.json"
OUTPUT_REPORT_FILE = DOCS_DIR / "quality_gate_report.json"
FRONTEND_ROUTE_CONTRACT_FILE = ROOT / "frontend" / "src" / "portal-shell" / "routeContracts.js"

GLOBAL_SELECTOR_PATTERN = re.compile(r"(^|\\s)(:root|body)\\b", re.MULTILINE)
FRONTEND_ROUTE_ENTRY_PATTERN = re.compile(
    r"""['"](?P<key>/[^'"]+)['"]\s*:\s*buildContract\(\s*{(?P<body>.*?)}\s*\)""",
    re.DOTALL,
)
FRONTEND_ROUTE_FIELD_PATTERN = re.compile(r"""route\s*:\s*['"](?P<route>/[^'"]+)['"]""")
FRONTEND_SCOPE_FIELD_PATTERN = re.compile(r"""scope\s*:\s*['"](?P<scope>[^'"]+)['"]""")
SHELL_TOKEN_VAR_PATTERN = re.compile(r"""var\(\s*(--portal-[\w-]+)(?P<fallback>\s*,[^)]*)?\)""")


@dataclass
class CheckReport:
    mode: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def note(self, message: str) -> None:
        self.info.append(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "passed": not self.errors,
        }


def _load_json(path: Path, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    return json.loads(path.read_text(encoding="utf-8"))


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _route_css_targets() -> dict[str, list[Path]]:
    return {
        "/wip-overview": [ROOT / "frontend/src/wip-overview/style.css"],
        "/wip-detail": [ROOT / "frontend/src/wip-detail/style.css"],
        "/hold-overview": [ROOT / "frontend/src/hold-overview/style.css"],
        "/hold-detail": [ROOT / "frontend/src/hold-detail/style.css"],
        "/hold-history": [ROOT / "frontend/src/hold-history/style.css"],
        "/resource": [ROOT / "frontend/src/resource-status/style.css"],
        "/resource-history": [ROOT / "frontend/src/resource-history/style.css"],
        "/qc-gate": [ROOT / "frontend/src/qc-gate/style.css"],
        "/job-query": [ROOT / "frontend/src/job-query/style.css"],
        "/admin/pages": [ROOT / "src/mes_dashboard/templates/admin/pages.html"],
        "/tables": [ROOT / "frontend/src/tables/style.css"],
        "/query-tool": [ROOT / "frontend/src/query-tool/style.css"],
        "/mid-section-defect": [ROOT / "frontend/src/mid-section-defect/style.css"],
        "/admin/dashboard": [ROOT / "frontend/src/admin-dashboard/style.css"],
    }


def _find_global_selectors(path: Path) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    selectors = []
    for match in GLOBAL_SELECTOR_PATTERN.finditer(text):
        selectors.append(match.group(2))
    return sorted(set(selectors))


def _find_shell_tokens_without_fallback(path: Path) -> list[str]:
    if not path.exists() or path.suffix.lower() != ".css":
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    missing: list[str] = []
    for match in SHELL_TOKEN_VAR_PATTERN.finditer(text):
        token = match.group(1)
        fallback = match.group("fallback")
        if fallback is None:
            missing.append(token)
    return sorted(set(missing))


def _check_scope_matrix(scope_matrix: dict[str, Any], report: CheckReport) -> tuple[set[str], set[str]]:
    in_scope = {
        str(item.get("route", "")).strip()
        for item in scope_matrix.get("in_scope", [])
        if str(item.get("route", "")).strip().startswith("/")
    }
    deferred = {
        str(item.get("route", "")).strip()
        for item in scope_matrix.get("deferred", [])
        if str(item.get("route", "")).strip().startswith("/")
    }
    if not in_scope:
        report.fail("scope matrix has no in-scope routes")
    if "/admin/pages" not in in_scope or "/admin/dashboard" not in in_scope:
        report.fail("scope matrix must include /admin/pages and /admin/dashboard")
    required_deferred: set[str] = set()
    if deferred != required_deferred:
        report.fail("scope matrix deferred routes mismatch expected policy (all routes promoted to in-scope)")
    return in_scope, deferred


def _check_route_contracts(
    route_contracts: dict[str, Any],
    in_scope: set[str],
    report: CheckReport,
) -> dict[str, dict[str, Any]]:
    required_fields = {
        "route",
        "route_id",
        "scope",
        "render_mode",
        "owner",
        "visibility_policy",
        "canonical_shell_path",
        "rollback_strategy",
    }
    routes = route_contracts.get("routes", [])
    if not isinstance(routes, list):
        report.fail("route contract file routes must be a list")
        return {}

    route_map: dict[str, dict[str, Any]] = {}
    for entry in routes:
        if not isinstance(entry, dict):
            report.fail("route contract entry must be object")
            continue
        route = str(entry.get("route", "")).strip()
        if not route.startswith("/"):
            report.fail(f"invalid route contract route: {route!r}")
            continue
        route_map[route] = entry
        missing = sorted(field for field in required_fields if not str(entry.get(field, "")).strip())
        if missing:
            report.fail(f"{route} missing required contract fields: {', '.join(missing)}")

    missing_routes = sorted(in_scope - set(route_map.keys()))
    if missing_routes:
        report.fail("in-scope routes missing contracts: " + ", ".join(missing_routes))

    for route in sorted(in_scope):
        entry = route_map.get(route)
        if not entry:
            continue
        if str(entry.get("scope", "")).strip() != "in-scope":
            report.fail(f"{route} must be scope=in-scope")
        if route.startswith("/admin/") and str(entry.get("visibility_policy", "")).strip() != "admin_only":
            report.fail(f"{route} must be admin_only visibility")
    return route_map


def _load_frontend_route_contract_inventory(
    path: Path,
    report: CheckReport,
) -> dict[str, str]:
    if not path.exists():
        report.fail(f"frontend route contract file missing: {_display_path(path)}")
        return {}

    text = path.read_text(encoding="utf-8")
    route_scopes: dict[str, str] = {}
    for match in FRONTEND_ROUTE_ENTRY_PATTERN.finditer(text):
        route_key = match.group("key")
        body = match.group("body")
        route_match = FRONTEND_ROUTE_FIELD_PATTERN.search(body)
        scope_match = FRONTEND_SCOPE_FIELD_PATTERN.search(body)
        if route_match is None:
            report.fail(f"{route_key} missing route field in frontend route contract")
            continue
        if scope_match is None:
            report.fail(f"{route_key} missing scope field in frontend route contract")
            continue

        route_value = route_match.group("route").strip()
        scope = scope_match.group("scope").strip()
        if route_value != route_key:
            report.fail(
                f"{route_key} frontend contract key/route mismatch "
                f"(route field: {route_value})"
            )
            continue
        route_scopes[route_key] = scope

    if not route_scopes:
        report.fail("frontend route contract inventory parse returned no routes")
    return route_scopes


def _check_frontend_backend_route_contract_parity(
    backend_route_map: dict[str, dict[str, Any]],
    frontend_route_scope_map: dict[str, str],
    report: CheckReport,
) -> None:
    backend_routes = set(backend_route_map.keys())
    frontend_routes = set(frontend_route_scope_map.keys())

    backend_only = sorted(backend_routes - frontend_routes)
    if backend_only:
        report.fail(
            "backend route contracts missing from frontend routeContracts.js: "
            + ", ".join(backend_only)
        )

    frontend_only = sorted(frontend_routes - backend_routes)
    if frontend_only:
        report.fail(
            "frontend routeContracts.js routes missing from backend route contracts: "
            + ", ".join(frontend_only)
        )

    for route in sorted(backend_routes & frontend_routes):
        backend_scope = str(backend_route_map[route].get("scope", "")).strip()
        frontend_scope = str(frontend_route_scope_map[route]).strip()
        if backend_scope != frontend_scope:
            report.fail(
                f"route scope mismatch for {route}: "
                f"backend={backend_scope!r}, frontend={frontend_scope!r}"
            )


def _check_quality_policy(
    quality_policy: dict[str, Any],
    deferred: set[str],
    report: CheckReport,
) -> str:
    configured_mode = str(quality_policy.get("severity_mode", {}).get("current", "warn")).strip().lower()
    if configured_mode not in {"warn", "block"}:
        report.fail("quality gate severity_mode.current must be warn or block")
        configured_mode = "warn"

    excluded = {
        str(route).strip()
        for route in quality_policy.get("deferred_routes_excluded", [])
        if str(route).strip().startswith("/")
    }
    if excluded != deferred:
        report.fail("quality gate deferred exclusion list must match scope matrix deferred list")
    return configured_mode


def _check_exception_registry(
    exception_registry: dict[str, Any],
    report: CheckReport,
) -> dict[str, dict[str, Any]]:
    entries = exception_registry.get("entries", [])
    if not isinstance(entries, list):
        report.fail("exception registry entries must be a list")
        return {}

    lookup: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            report.fail("exception entry must be object")
            continue
        entry_id = str(entry.get("id", "")).strip()
        scope = str(entry.get("scope", "")).strip()
        owner = str(entry.get("owner", "")).strip()
        milestone = str(entry.get("milestone", "")).strip()
        if not entry_id:
            report.fail("exception entry missing id")
            continue
        if not scope.startswith("/"):
            report.fail(f"{entry_id} missing valid scope route")
        if not owner:
            report.fail(f"{entry_id} missing owner")
        if not milestone:
            report.fail(f"{entry_id} missing milestone")
        lookup[scope] = entry
    return lookup


def _check_style_governance(
    in_scope: set[str],
    exception_by_scope: dict[str, dict[str, Any]],
    report: CheckReport,
) -> None:
    route_targets = _route_css_targets()
    for route in sorted(in_scope):
        for path in route_targets.get(route, []):
            selectors = _find_global_selectors(path)
            if selectors:
                if route in exception_by_scope:
                    report.warn(
                        f"{route} uses global selectors {selectors} in {_display_path(path)} "
                        "with approved exception"
                    )
                else:
                    report.fail(
                        f"{route} uses global selectors {selectors} in {_display_path(path)} "
                        "without exception"
                    )
            missing_shell_fallbacks = _find_shell_tokens_without_fallback(path)
            if not missing_shell_fallbacks:
                continue
            if route in exception_by_scope:
                report.warn(
                    f"{route} uses shell tokens without fallback {missing_shell_fallbacks} "
                    f"in {_display_path(path)} with approved exception"
                )
                continue
            report.fail(
                f"{route} uses shell tokens without fallback {missing_shell_fallbacks} "
                f"in {_display_path(path)}"
            )


def _check_asset_readiness(
    asset_manifest: dict[str, Any],
    deferred: set[str],
    report: CheckReport,
) -> None:
    required = asset_manifest.get("in_scope_required_assets", {})
    if not isinstance(required, dict) or not required:
        report.fail("asset readiness manifest missing in_scope_required_assets")
        return

    declared_deferred = {
        str(route).strip()
        for route in asset_manifest.get("deferred_routes", [])
        if str(route).strip().startswith("/")
    }
    if declared_deferred != deferred:
        report.fail("asset readiness deferred route list must match scope matrix")

    dist_dir = ROOT / "src/mes_dashboard/static/dist"
    for route, assets in sorted(required.items()):
        if not isinstance(assets, list) or not assets:
            report.fail(f"asset manifest route {route} must define non-empty asset list")
            continue
        for filename in assets:
            if not isinstance(filename, str) or not filename.strip():
                report.fail(f"asset manifest route {route} contains invalid filename")
                continue
            asset_path = dist_dir / filename
            if not asset_path.exists():
                report.warn(f"missing dist asset for {route}: {filename}")


def _check_content_safety(
    known_bug_baseline: dict[str, Any],
    manual_acceptance: dict[str, Any],
    bug_revalidation: dict[str, Any],
    in_scope: set[str],
    report: CheckReport,
) -> None:
    baseline_routes = set((known_bug_baseline.get("routes") or {}).keys())
    missing_baselines = sorted(in_scope - baseline_routes)
    if missing_baselines:
        report.fail("known bug baseline missing routes: " + ", ".join(missing_baselines))

    records = manual_acceptance.get("records", [])
    if not isinstance(records, list):
        report.fail("manual acceptance records must be a list")
    replay_records = bug_revalidation.get("records", [])
    if not isinstance(replay_records, list):
        report.fail("bug revalidation records must be a list")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("warn", "block"),
        default=None,
        help="Gate severity mode override (default: use quality_gate_policy.json)",
    )
    parser.add_argument(
        "--report",
        default=str(OUTPUT_REPORT_FILE),
        help="Output report JSON path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    scope_matrix = _load_json(SCOPE_MATRIX_FILE)
    route_contracts = _load_json(ROUTE_CONTRACT_FILE)
    exception_registry = _load_json(EXCEPTION_REGISTRY_FILE)
    quality_policy = _load_json(QUALITY_POLICY_FILE)
    asset_manifest = _load_json(ASSET_MANIFEST_FILE)
    known_bug_baseline = _load_json(KNOWN_BUG_BASELINE_FILE)
    manual_acceptance = _load_json(MANUAL_ACCEPTANCE_FILE, default={"records": []})
    bug_revalidation = _load_json(BUG_REVALIDATION_FILE, default={"records": []})
    _ = _load_json(STYLE_INVENTORY_FILE, default={})

    report = CheckReport(mode=args.mode or "warn")
    in_scope, deferred = _check_scope_matrix(scope_matrix, report)
    backend_route_map = _check_route_contracts(route_contracts, in_scope, report)
    frontend_route_scope_map = _load_frontend_route_contract_inventory(FRONTEND_ROUTE_CONTRACT_FILE, report)
    _check_frontend_backend_route_contract_parity(backend_route_map, frontend_route_scope_map, report)
    configured_mode = _check_quality_policy(quality_policy, deferred, report)
    report.mode = args.mode or configured_mode
    exception_by_scope = _check_exception_registry(exception_registry, report)
    _check_style_governance(in_scope, exception_by_scope, report)
    _check_asset_readiness(asset_manifest, deferred, report)
    _check_content_safety(known_bug_baseline, manual_acceptance, bug_revalidation, in_scope, report)

    output_path = Path(args.report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if report.mode == "block" and report.errors:
        print(f"[BLOCK] modernization gates failed with {len(report.errors)} error(s)")
        for error in report.errors:
            print(f"- {error}")
        return 1

    if report.errors:
        print(f"[WARN] modernization gates found {len(report.errors)} error(s) but mode is warn")
        for error in report.errors:
            print(f"- {error}")
    else:
        print("[OK] modernization gates passed")

    if report.warnings:
        print(f"[WARN] additional warnings: {len(report.warnings)}")
        for warning in report.warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
