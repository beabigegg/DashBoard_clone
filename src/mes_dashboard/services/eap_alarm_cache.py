# -*- coding: utf-8 -*-
"""EAP ALARM spool cache helpers.

Governs:
  - _SCHEMA_VERSION  (EA-06): bump on any parquet column change
  - Spool directory / TTL from env (EAP_ALARM_SPOOL_DIR, EAP_ALARM_SPOOL_TTL)
  - Spool key construction (EA-01)
  - AlarmCategory decode table (EA-05)
  - Spool exists / path / TTL helpers (mirrors reject_dataset_cache pattern)
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── EA-06: schema version — bump on any parquet column add/remove/rename ──────
# v4: added product-dim columns PJ_TYPE / PRODUCT_LINE / PJ_BOP
#     (LOT_ID → DWH.DW_MES_CONTAINER lookup at spool-write time)
_SCHEMA_VERSION: int = 4

# ── Environment configuration ─────────────────────────────────────────────────
EAP_ALARM_SPOOL_DIR: str = os.getenv(
    "EAP_ALARM_SPOOL_DIR", "tmp/query_spool/eap_alarm"
)
EAP_ALARM_SPOOL_TTL: int = max(
    3600, int(os.getenv("EAP_ALARM_SPOOL_TTL", "72000"))
)

# ── EA-01: Spool key construction ─────────────────────────────────────────────

def make_eap_alarm_spool_key(
    date_from: Optional[str],
    date_to: Optional[str],
    eqp_types: list[str],
    lot_ids: tuple[str, ...] | list[str] = (),
    pj_types: tuple[str, ...] | list[str] = (),
    product_lines: tuple[str, ...] | list[str] = (),
    pj_bops: tuple[str, ...] | list[str] = (),
) -> str:
    """Build the deterministic spool key for a coarse EAP ALARM query (EA-01).

    Format: ``eap_alarm_{date_from}_{date_to}_{coarse_dims_hash8}_v{schema_version}``

    Uses underscores (not colons) so the key passes query_spool_store's
    _VALID_ID_RE = r"^[A-Za-z0-9._-]{4,128}$" and can be used directly as
    a Redis metadata key and parquet filename without secondary sanitization.

    The hash covers all 5 coarse dims sorted with fixed per-dim separators:
      eqp_types | lot_ids (whitespace-stripped) | pj_types | product_lines | pj_bops
    Each dim is independently delimited so empty lists cannot collide across dims
    (EA-01 canonical repr, D-1).

    Raises:
        ValueError: if date_from or date_to is missing (EA-03 guard).
    """
    if not date_from or not date_to:
        raise ValueError("LAST_UPDATE_TIME filter required (date_from and date_to must be provided)")

    # Canonicalize each dim: sorted, stripped, distinct per-dim separator prevents
    # cross-dim hash collisions when some dims are empty.
    eqp_part = "eqp:" + ",".join(sorted(eqp_types))
    lot_part = "lot:" + ",".join(sorted(str(v).strip() for v in lot_ids if str(v).strip()))
    pjt_part = "pjt:" + ",".join(sorted(str(v).strip() for v in pj_types if str(v).strip()))
    pln_part = "pln:" + ",".join(sorted(str(v).strip() for v in product_lines if str(v).strip()))
    bop_part = "bop:" + ",".join(sorted(str(v).strip() for v in pj_bops if str(v).strip()))

    canonical = "|".join([eqp_part, lot_part, pjt_part, pln_part, bop_part])
    dims_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]

    return f"eap_alarm_{date_from}_{date_to}_{dims_hash}_v{_SCHEMA_VERSION}"


# ── Spool file path helpers ───────────────────────────────────────────────────

# ── EA-05: AlarmCategory decode table ────────────────────────────────────────

_ALARM_CATEGORY_MAP: dict[int, str] = {
    0: "非分類",
    1: "設備",
    2: "製程",
    3: "視覺",
    4: "機械",
    5: "電子",
    6: "通知/供料",
    7: "品質",
    64: "繼續錯誤",
}


def decode_alarm_category(code) -> str:
    """Decode ALARM_CATEGORY_CODE (EA-05) to a human-readable label.

    Accepts int, float, or string; returns "未知" for None or unknown codes.
    """
    if code is None:
        return "未知"
    try:
        code_int = int(float(code))
    except (TypeError, ValueError):
        return "未知"
    return _ALARM_CATEGORY_MAP.get(code_int, "未知")


# ── Spool file path helpers ───────────────────────────────────────────────────

def get_eap_alarm_spool_path(spool_key: str) -> str:
    """Return the absolute parquet file path for a given spool key."""
    spool_dir = EAP_ALARM_SPOOL_DIR
    if not os.path.isabs(spool_dir):
        spool_dir = os.path.join(os.getcwd(), spool_dir)
    return os.path.join(spool_dir, f"{spool_key}.parquet")
