# -*- coding: utf-8 -*-
"""UPH Performance spool cache helpers.

Governs:
  - _SCHEMA_VERSION: bump on any parquet column add/remove/rename (data-shape
    §3.29 breaking-change surface).
  - Spool key construction (data-shape §3.29 Spool key composition) -- mirrors
    eap_alarm_cache.make_eap_alarm_spool_key's canonical-repr shape.
  - Spool staging path helper used ONLY inside the worker before
    register_spool_file() moves the file into the canonical
    query_spool_store location (mirrors eap_alarm_cache.get_eap_alarm_spool_path).

No dedicated UPH_PERFORMANCE_SPOOL_DIR / _SPOOL_TTL env vars exist
(env-contract.md §Async Worker -- UPH Performance Query): this feature reuses
the shared QUERY_SPOOL_DIR base directory (namespace subdirectory
`uph_performance/`) and query_spool_store's QUERY_SPOOL_TTL_SECONDS default,
mirroring production-achievement-async-spool's precedent exactly.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Optional

# data-shape-contract.md §3.29 Spool parquet schema.
# Bump on any parquet column add/remove/rename.
#   v1 -> v2: added MODEL (RESOURCEFAMILYNAME) column to the spool so the real
#             機型 is a visible trend/detail dimension (add-uph-performance-page
#             redesign). Old v1 spools carry a different key suffix and simply
#             age out via TTL -- no forced purge needed (ephemeral spool).
_SCHEMA_VERSION: int = 2

_NAMESPACE = "uph_performance"


def _canon_part(prefix: str, values: Optional[Iterable[str]], upper: bool = False) -> str:
    cleaned = {str(v).strip() for v in (values or []) if str(v).strip()}
    if upper:
        cleaned = {v.upper() for v in cleaned}
    return f"{prefix}:" + ",".join(sorted(cleaned))


def make_uph_performance_spool_key(
    date_from: Optional[str],
    date_to: Optional[str],
    families: Optional[Iterable[str]] = (),
    workcenter_names: Optional[Iterable[str]] = (),
    packages: Optional[Iterable[str]] = (),
    pj_types: Optional[Iterable[str]] = (),
    equipment_ids: Optional[Iterable[str]] = (),
    models: Optional[Iterable[str]] = (),
) -> str:
    """Build the deterministic spool key for a coarse UPH Performance query.

    Format: ``uph_performance_{date_from}_{date_to}_{coarse_dims_hash8}_v{schema_version}``

    Canonical repr (sorted, per-dim separated so empty dims cannot collide,
    data-shape-contract.md §3.29 Spool key composition): date_from, date_to,
    families (closed enum subset of {GDBA, GWBA}; empty/absent = both),
    models (RESOURCEFAMILYNAME, e.g. DBA_AD832UR -- the real 機型, replaces the
    GDBA/GWBA-only selector), workcenter_names, packages (PRODUCTLINENAME),
    pj_types (PJ_TYPE), equipment_ids (whitespace-stripped). _SCHEMA_VERSION
    participates in the key.

    Note: the ranking endpoint's own pj_type[] fine filter is deliberately
    NOT part of this key (design.md Key Decisions; it re-slices the
    already-built global-scope spool client-of-spool).

    Raises:
        ValueError: if date_from or date_to is missing (UPH-01 guard, mirrors EA-03).
    """
    if not date_from or not date_to:
        raise ValueError("LAST_UPDATE_TIME filter required (date_from and date_to must be provided)")

    canonical = "|".join([
        _canon_part("fam", families, upper=True),
        _canon_part("mdl", models),
        _canon_part("wc", workcenter_names),
        _canon_part("pkg", packages),
        _canon_part("pjt", pj_types),
        _canon_part("eqp", equipment_ids),
    ])
    dims_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]

    return f"{_NAMESPACE}_{date_from}_{date_to}_{dims_hash}_v{_SCHEMA_VERSION}"


def get_uph_performance_spool_path(spool_key: str) -> str:
    """Return the staging parquet path for *spool_key* (worker-internal only).

    Used ONLY inside UphPerformanceJob.post_aggregate() before
    register_spool_file() moves the written parquet into the canonical
    query_spool_store location. Routes must resolve the canonical (already
    registered) path via query_spool_store.get_spool_file_path("uph_performance", ...)
    instead -- mirrors production_achievement_worker.py's pre_query pattern
    (no dedicated env var; reuses the shared QUERY_SPOOL_DIR base).
    """
    from mes_dashboard.core.query_spool_store import QUERY_SPOOL_DIR

    spool_dir = QUERY_SPOOL_DIR / _NAMESPACE
    return str(spool_dir / f"{spool_key}.parquet")
