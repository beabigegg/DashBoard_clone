# -*- coding: utf-8 -*-
"""AI Tool Definitions — converts YAML registry entries to LLM-readable prompt blocks.

Two-tier strategy:
  Tier 1: 8-10 high-frequency tools always included in the agent system prompt.
  Tier 2: remaining tools discoverable via `search_tools` meta-tool.
"""

from __future__ import annotations

from typing import Any

from mes_dashboard.services.ai_function_registry import REGISTRY

# ---------------------------------------------------------------------------
# Tier 1 tools — always included in the agent system prompt
# ---------------------------------------------------------------------------

TIER_1_TOOLS = [
    "reject_summary",
    "reject_reason_pareto",
    "reject_trend",
    "wip_summary",
    "wip_matrix",
    "dashboard_kpi",
    "ou_trend",
    "yield_summary",
    "hold_overview_treemap",
    "equipment_status_summary",
]


def build_single_tool_description(name: str, entry: dict[str, Any]) -> str:
    """Convert a single YAML registry entry into a prompt-friendly text description.

    Format:
        ### <name>
        說明：<description>
        參數：
          - <param_name> (<type>, 必填|選填[, 預設=<default>][, 可選值=<enum>]): <description>
    """
    lines = [f"### {name}", f"說明：{entry.get('description', '')}"]

    params = entry.get("params") or {}
    if params:
        lines.append("參數：")
        for pname, pspec in params.items():
            required = "必填" if pspec.get("required") else "選填"
            ptype = pspec.get("type", "string")
            desc = pspec.get("description", "")
            extras = []
            if pspec.get("default") is not None:
                extras.append(f"預設={pspec['default']}")
            enum_vals = pspec.get("enum")
            if enum_vals:
                # Limit enum display to avoid blowing up token count
                if len(enum_vals) <= 10:
                    extras.append(f"可選值={enum_vals}")
                else:
                    sample = enum_vals[:5]
                    extras.append(f"可選值範例={sample}…共{len(enum_vals)}個")
            extra_str = (", " + ", ".join(extras)) if extras else ""
            lines.append(f"  - {pname} ({ptype}, {required}{extra_str}): {desc}")
    else:
        lines.append("參數：（無）")

    return "\n".join(lines)


def build_tool_prompt_block() -> str:
    """Assemble Tier 1 tool descriptions + special tools into a ~1,500-token prompt block."""
    sections: list[str] = []

    # Tier 1 YAML tools
    for name in TIER_1_TOOLS:
        entry = REGISTRY.get(name)
        if entry is None:
            continue
        sections.append(build_single_tool_description(name, entry))

    # Special tools (hardcoded, not in YAML)
    sections.append(
        "### query_database\n"
        "說明：以自然語言提問，系統自動生成 SQL 查詢資料庫\n"
        "參數：\n"
        "  - question (string, 必填): 要查詢的問題（中文自然語言）"
    )
    sections.append(
        "### search_tools\n"
        "說明：搜尋更多可用工具（Tier 2），依關鍵字過濾\n"
        "參數：\n"
        "  - keyword (string, 必填): 搜尋關鍵字（中文或英文）"
    )

    return "\n\n".join(sections)
