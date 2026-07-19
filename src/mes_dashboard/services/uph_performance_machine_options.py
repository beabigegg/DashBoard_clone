# -*- coding: utf-8 -*-
"""UPH Performance machine-options cache (add-uph-performance-page redesign).

Pre-query dropdown options for the UPH filter bar, sourced from the equipment
master ``DWH.DW_MES_RESOURCE`` (OBJECTCATEGORY='ASSEMBLY', GDBA/GWBA scope).

Replaces the old GDBA/GWBA-only 機型 selector and the free-text 工作站 /
機台 textareas with real, cascadable dropdown values:

  - family (GDBA=Die-Bond / GWBA=Wire-Bond)  <- SUBSTR(RESOURCENAME, 1, 4)
  - model  (機型, e.g. DBA_AD832UR / WBA_iHawk) <- RESOURCEFAMILYNAME
  - workcenter (工作站, e.g. 焊接_DB)          <- WORKCENTERNAME
  - equipment_id (機台, e.g. GDBA-0131)        <- RESOURCENAME

The full per-equipment mapping is returned so the frontend can cascade
(family -> model -> workcenter -> equipment) entirely client-side.

Equipment master is slow-changing, so this uses a simple in-process TTL cache
(per gunicorn worker) rather than container_filter_cache's Redis-L2 machinery
-- the query is a single ~400-row scan.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mes_dashboard.uph_performance_machine_options")

# GDBA=Die-Bond, GWBA=Wire-Bond -- the DB/WB quick-category labels (UPH-02).
_FAMILY_LABELS: Dict[str, str] = {"GDBA": "Die-Bond", "GWBA": "Wire-Bond"}

_MACHINE_OPTIONS_SQL = """
SELECT
    TRIM(r.RESOURCENAME)              AS EQUIPMENT_ID,
    SUBSTR(TRIM(r.RESOURCENAME), 1, 4) AS FAMILY,
    TRIM(r.RESOURCEFAMILYNAME)       AS MODEL,
    TRIM(r.WORKCENTERNAME)           AS WORKCENTER
FROM DWH.DW_MES_RESOURCE r
WHERE r.OBJECTCATEGORY = 'ASSEMBLY'
  AND (r.RESOURCENAME LIKE 'GDBA%' OR r.RESOURCENAME LIKE 'GWBA%')
  AND r.RESOURCENAME IS NOT NULL
"""

# Slow-changing equipment master -> 1h in-process TTL.
_TTL_SECONDS = 3600
_QUERY_TIMEOUT_SECONDS = 60

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None
_cache_ts: float = 0.0


def _query_oracle() -> Dict[str, Any]:
    """Query DW_MES_RESOURCE and shape the cascadable options payload."""
    from mes_dashboard.core.database import read_sql_df_slow

    df = read_sql_df_slow(
        _MACHINE_OPTIONS_SQL,
        params={},
        timeout_seconds=_QUERY_TIMEOUT_SECONDS,
        caller="uph_performance_machine_options",
    )

    equipment: List[Dict[str, str]] = []
    for _, row in df.iterrows():
        eqid = (str(row.get("EQUIPMENT_ID") or "")).strip()
        family = (str(row.get("FAMILY") or "")).strip().upper()
        if not eqid or family not in _FAMILY_LABELS:
            continue
        model = (str(row.get("MODEL") or "")).strip()
        workcenter = (str(row.get("WORKCENTER") or "")).strip()
        equipment.append({
            "equipment_id": eqid,
            "family": family,
            "model": model or None,
            "workcenter": workcenter or None,
        })

    equipment.sort(key=lambda e: e["equipment_id"])

    # Distinct convenience lists (frontend can also derive these from `equipment`).
    families = [
        {"code": code, "label": _FAMILY_LABELS[code]}
        for code in ("GDBA", "GWBA")
        if any(e["family"] == code for e in equipment)
    ]
    seen_models = set()
    models: List[Dict[str, str]] = []
    for e in equipment:
        key = (e["family"], e["model"])
        if e["model"] and key not in seen_models:
            seen_models.add(key)
            models.append({"family": e["family"], "model": e["model"]})
    models.sort(key=lambda m: (m["family"], m["model"]))
    workcenters = sorted({e["workcenter"] for e in equipment if e["workcenter"]})

    return {
        "families": families,
        "models": models,
        "workcenters": workcenters,
        "equipment": equipment,
    }


def get_machine_options(force: bool = False) -> Dict[str, Any]:
    """Return cascadable UPH machine-filter options (cached, per-worker TTL).

    Shape (data-shape-contract.md §3.29a UPH machine-options):
        {
          "families":    [{"code": "GDBA", "label": "Die-Bond"}, ...],
          "models":      [{"family": "GDBA", "model": "DBA_AD832UR"}, ...],
          "workcenters": ["焊接_DB", "焊接_DW", "焊接_WB"],
          "equipment":   [{"equipment_id","family","model","workcenter"}, ...],
        }

    ``force=True`` bypasses the TTL and re-queries Oracle.
    """
    global _cache, _cache_ts

    with _lock:
        now = time.monotonic()
        if not force and _cache is not None and (now - _cache_ts) < _TTL_SECONDS:
            return _cache
        data = _query_oracle()
        _cache = data
        _cache_ts = now
        logger.info(
            "uph_performance_machine_options: refreshed (equipment=%d models=%d workcenters=%d)",
            len(data["equipment"]), len(data["models"]), len(data["workcenters"]),
        )
        return data
