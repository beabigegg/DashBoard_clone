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
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── EA-06: schema version — bump on any parquet column add/remove/rename ──────
_SCHEMA_VERSION: int = 1

# ── Environment configuration ─────────────────────────────────────────────────
EAP_ALARM_SPOOL_DIR: str = os.getenv(
    "EAP_ALARM_SPOOL_DIR", "tmp/query_spool/eap_alarm"
)
EAP_ALARM_SPOOL_TTL: int = max(
    3600, int(os.getenv("EAP_ALARM_SPOOL_TTL", "72000"))
)

# ── EA-05: AlarmCategory decode table ─────────────────────────────────────────
_ALARM_CATEGORY_DECODE: dict[int, str] = {
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

_ALARM_CATEGORY_UNKNOWN: str = "未知"


def decode_alarm_category(code) -> str:
    """Decode an integer AlarmCategory code to its display label (EA-05).

    Any unknown or None code returns "未知" (never crashes).
    """
    if code is None:
        return _ALARM_CATEGORY_UNKNOWN
    try:
        int_code = int(code)
    except (TypeError, ValueError):
        return _ALARM_CATEGORY_UNKNOWN
    return _ALARM_CATEGORY_DECODE.get(int_code, _ALARM_CATEGORY_UNKNOWN)


# ── EA-01: Spool key construction ─────────────────────────────────────────────

def make_eap_alarm_spool_key(
    date_from: Optional[str],
    date_to: Optional[str],
    eqp_types: list[str],
) -> str:
    """Build the deterministic spool key for a coarse EAP ALARM query (EA-01).

    Format: ``eap_alarm_{date_from}_{date_to}_{sorted_eqp_types_hash8}_v{schema_version}``

    Uses underscores (not colons) so the key passes query_spool_store's
    _VALID_ID_RE = r"^[A-Za-z0-9._-]{4,128}$" and can be used directly as
    a Redis metadata key and parquet filename without secondary sanitization.

    The hash covers the sorted, comma-joined EQP-type list so that any
    permutation of the same type set maps to the same key.

    Raises:
        ValueError: if date_from or date_to is missing (EA-03 guard).
    """
    if not date_from or not date_to:
        raise ValueError("LAST_UPDATE_TIME filter required (date_from and date_to must be provided)")

    sorted_types = sorted(eqp_types)
    type_string = ",".join(sorted_types)
    type_hash = hashlib.sha256(type_string.encode("utf-8")).hexdigest()[:8]

    return f"eap_alarm_{date_from}_{date_to}_{type_hash}_v{_SCHEMA_VERSION}"


# ── Equipment ID expansion from Redis cache ───────────────────────────────────

def get_equipment_ids_for_types(
    eqp_types: list[str],
    redis_client=None,
) -> list[str] | None:
    """Return EQUIPMENT_ID list for the given EQP type prefixes from the Redis
    equipment-status cache (e.g. ['GDBA','GWBK'] → ['GDBA-0212','GDBA-0229',...]).

    Reads ``{prefix}:equipment_status:data`` (written by realtime_equipment_cache).
    Returns None on any cache miss or error so callers can fall back to SUBSTR.

    The result is used to build ``EQUIPMENT_ID IN (...)`` Oracle clauses which
    can use the C_TEST_EQUIPMENT_ID index, unlike SUBSTR-based filters.
    """
    try:
        if redis_client is None:
            from mes_dashboard.core.redis_client import get_redis_client
            redis_client = get_redis_client()

        from mes_dashboard.core.redis_client import get_key_prefix
        from mes_dashboard.config.constants import EQUIPMENT_STATUS_DATA_KEY

        data_key = f"{get_key_prefix()}:{EQUIPMENT_STATUS_DATA_KEY}"
        raw = redis_client.get(data_key)
        if not raw:
            return None

        records: list[dict] = json.loads(raw)
        type_set = set(eqp_types)
        ids = [
            r["EQUIPMENTID"]
            for r in records
            if r.get("EQUIPMENTID") and r["EQUIPMENTID"][:4] in type_set
        ]
        return ids if ids else None
    except Exception as exc:
        logger.warning("get_equipment_ids_for_types: cache miss, falling back to SUBSTR: %s", exc)
        return None


# ── Spool file path helpers ───────────────────────────────────────────────────

def get_eap_alarm_spool_path(spool_key: str) -> str:
    """Return the absolute parquet file path for a given spool key."""
    spool_dir = EAP_ALARM_SPOOL_DIR
    if not os.path.isabs(spool_dir):
        spool_dir = os.path.join(os.getcwd(), spool_dir)
    return os.path.join(spool_dir, f"{spool_key}.parquet")
