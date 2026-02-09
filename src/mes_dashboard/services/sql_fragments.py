# -*- coding: utf-8 -*-
"""Shared SQL fragments/constants for cache-oriented services.

Centralizing common Oracle table/view references reduces drift across
resource/equipment cache implementations.
"""

from __future__ import annotations

RESOURCE_TABLE = "DWH.DW_MES_RESOURCE"
# NOTE:
# QueryBuilder.build() only replaces the exact token "{{ WHERE_CLAUSE }}".
# Keep this token literal (double braces) in shared SQL templates.
RESOURCE_BASE_SELECT_TEMPLATE = (
    f"SELECT * FROM {RESOURCE_TABLE} {{{{ WHERE_CLAUSE }}}}"
)
RESOURCE_VERSION_SELECT_TEMPLATE = (
    f"SELECT MAX(LASTCHANGEDATE) as VERSION FROM {RESOURCE_TABLE} {{{{ WHERE_CLAUSE }}}}"
)

EQUIPMENT_STATUS_VIEW = "DWH.DW_MES_EQUIPMENTSTATUS_WIP_V"
EQUIPMENT_STATUS_COLUMNS: tuple[str, ...] = (
    "RESOURCEID",
    "EQUIPMENTID",
    "OBJECTCATEGORY",
    "EQUIPMENTASSETSSTATUS",
    "EQUIPMENTASSETSSTATUSREASON",
    "JOBORDER",
    "JOBMODEL",
    "JOBSTAGE",
    "JOBID",
    "JOBSTATUS",
    "CREATEDATE",
    "CREATEUSERNAME",
    "CREATEUSER",
    "TECHNICIANUSERNAME",
    "TECHNICIANUSER",
    "SYMPTOMCODE",
    "CAUSECODE",
    "REPAIRCODE",
    "RUNCARDLOTID",
    "LOTTRACKINQTY_PCS",
    "LOTTRACKINTIME",
    "LOTTRACKINEMPLOYEE",
)

EQUIPMENT_STATUS_SELECT_SQL = (
    "SELECT\n    "
    + ",\n    ".join(EQUIPMENT_STATUS_COLUMNS)
    + f"\nFROM {EQUIPMENT_STATUS_VIEW}"
)
