# -*- coding: utf-8 -*-
"""EAP ALARM RQ worker.

Entry point: run_eap_alarm_query_job(job_id, date_from, date_to, eqp_types)

Design constraints (ADR-0008, design.md):
  - Oracle connections established POST-FORK inside the job fn (never at import).
  - Uses read_sql_df_slow (slow pool / long timeout).
  - Progress milestones: 5 → 15 → 90 → 100 (coarse bracket; EA-inner-fn cannot
    accept per-chunk callback — cache-spool-patterns "Type B coarse bracket" rule).
  - Writes 10-column parquet to eap_alarm spool namespace.
  - AlarmCategory decoded at spool-write time (EA-05).
  - DETAIL EAV params folded into DETAIL_PARAMS JSON string at spool-write time (EA-04).

Module-level register_job_type() side-effect fires at import time (job-registry-central).
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("mes_dashboard.eap_alarm_worker")

# ── Env configuration (read at import; workers load env before import) ─────────
EAP_ALARM_JOB_TIMEOUT_SECONDS: int = max(
    60, int(os.getenv("EAP_ALARM_JOB_TIMEOUT_SECONDS", "1800"))
)
EAP_ALARM_WORKER_QUEUE: str = os.getenv("EAP_ALARM_WORKER_QUEUE", "eap-alarm-query")
EAP_ALARM_JOB_TTL_SECONDS: int = max(
    3600, int(os.getenv("EAP_ALARM_SPOOL_TTL", "72000"))
)

_JOB_PREFIX = "eap-alarm"

# ── Oracle SQL template (EA-03/EA-04) ─────────────────────────────────────────
# EAP_EVENT columns: SEQ_ID, EQUIPMENT_ID, LOT_ID, PN, EVENT_NAME, EVENT_REF_ID,
#   EVENT_TYPE, LAST_UPDATE_TIME, EVENT_DATE
# ALARM_TEXT maps to EVENT_NAME directly (numeric alarm codes like '267', '8480').
# ALARM_CATEGORY_CODE has no source column — persisted as NULL.
# {equipment_filter} is filled at runtime; see _build_equipment_filter().
_EAP_EVENT_SQL_TEMPLATE = """\
SELECT
    TO_CHAR(e.SEQ_ID) AS EVENT_ID,
    e.EQUIPMENT_ID AS EQP_ID,
    SUBSTR(e.EQUIPMENT_ID, 1, 4) AS EQP_TYPE,
    e.LOT_ID,
    e.EVENT_NAME AS ALARM_TEXT,
    NULL AS ALARM_CATEGORY_CODE,
    e.LAST_UPDATE_TIME AS ALARM_TIME
FROM DWH.EAP_EVENT e
WHERE e.LAST_UPDATE_TIME BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD')
                              AND TO_DATE(:date_to, 'YYYY-MM-DD') + 1
  AND {equipment_filter}
  AND e.EVENT_TYPE = 'EQP_SECS_ALARM'
"""

# DETAIL_PARAMS: all EAP_EVENT_DETAIL parameters for each event.
# EAP_EVENT_DETAIL columns: SEQ_ID, PARAMETER_NAME, PARAMETER_VALUE, PARAMETER_ID
_EXCLUDED_DETAIL_PARAMS: set = set()  # no parameters to exclude in current schema

_DETAIL_PARAMS_SQL_TEMPLATE = """\
SELECT TO_CHAR(e.SEQ_ID) AS EVENT_ID, d.PARAMETER_NAME, d.PARAMETER_VALUE
FROM DWH.EAP_EVENT e
JOIN DWH.EAP_EVENT_DETAIL d ON d.SEQ_ID = e.SEQ_ID
WHERE e.LAST_UPDATE_TIME BETWEEN TO_DATE(:date_from, 'YYYY-MM-DD')
                              AND TO_DATE(:date_to, 'YYYY-MM-DD') + 1
  AND {equipment_filter}
  AND e.EVENT_TYPE = 'EQP_SECS_ALARM'
"""

# Parquet columns order per §3.17
_PARQUET_COLUMNS = [
    "EVENT_ID", "EQP_ID", "EQP_TYPE", "LOT_ID",
    "ALARM_TEXT", "ALARM_CATEGORY_CODE", "ALARM_CATEGORY",
    "ALARM_TIME", "DETAIL_PARAMS", "eqp_types_filter",
]


def run_eap_alarm_query_job(
    job_id: str,
    date_from: str,
    date_to: str,
    eqp_types: List[str],
) -> None:
    """RQ worker entry point: Oracle JOIN → decode → parquet write.

    All Oracle connections opened post-fork inside this function (ADR-0004).
    Progress milestones: 5 (start) → 15 (Oracle connected) → 90 (parquet written) → 100 (done).
    """
    from mes_dashboard.rq_worker_preload import ensure_rq_logging
    ensure_rq_logging()

    from mes_dashboard.services.async_query_job_service import (
        complete_job,
        update_job_progress,
    )
    from mes_dashboard.services.eap_alarm_cache import (
        decode_alarm_category,
        make_eap_alarm_spool_key,
        get_eap_alarm_spool_path,
        EAP_ALARM_SPOOL_TTL,
    )

    logger.info("eap_alarm_worker: job started job_id=%s", job_id)
    update_job_progress(_JOB_PREFIX, job_id, status="started", progress="initializing", pct="5")

    try:
        # Build spool key and path
        spool_key = make_eap_alarm_spool_key(date_from, date_to, eqp_types)
        spool_path = get_eap_alarm_spool_path(spool_key)
        import os
        os.makedirs(os.path.dirname(spool_path), exist_ok=True)

        # EA-01: hash for eqp_types_filter column
        import hashlib
        sorted_types = sorted(eqp_types)
        type_hash = hashlib.sha256(",".join(sorted_types).encode("utf-8")).hexdigest()[:8]

        # Build Oracle equipment filter — prefer EQUIPMENT_ID IN (...) via Redis
        # cache so Oracle can use the C_TEST_EQUIPMENT_ID index; fall back to
        # SUBSTR(EQUIPMENT_ID,1,4) IN (...) when cache is cold.
        from mes_dashboard.services.eap_alarm_cache import get_equipment_ids_for_types
        equipment_ids = get_equipment_ids_for_types(eqp_types)

        if equipment_ids:
            logger.info(
                "eap_alarm_worker: using cache-expanded filter (%d equipment IDs) job_id=%s",
                len(equipment_ids), job_id,
            )
            placeholders = ", ".join(f":r{i}" for i in range(len(equipment_ids)))
            equipment_filter = f"e.EQUIPMENT_ID IN ({placeholders})"
            eqp_params: Dict[str, Any] = {f"r{i}": eid for i, eid in enumerate(equipment_ids)}
        else:
            logger.info(
                "eap_alarm_worker: cache cold, using SUBSTR filter for %s job_id=%s",
                eqp_types, job_id,
            )
            n = len(eqp_types)
            placeholders = ", ".join(f":eqp{i}" for i in range(n))
            equipment_filter = f"SUBSTR(e.EQUIPMENT_ID, 1, 4) IN ({placeholders})"
            eqp_params = {f"eqp{i}": t for i, t in enumerate(eqp_types)}

        sql = _EAP_EVENT_SQL_TEMPLATE.format(equipment_filter=equipment_filter)
        params: Dict[str, Any] = {"date_from": date_from, "date_to": date_to, **eqp_params}

        # Post-fork Oracle connection (ADR-0004)
        logger.info("eap_alarm_worker: connecting to Oracle job_id=%s", job_id)
        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="querying Oracle", pct="15")

        from mes_dashboard.core.database import read_sql_df_slow
        df = read_sql_df_slow(
            sql,
            params=params,
            timeout_seconds=EAP_ALARM_JOB_TIMEOUT_SECONDS,
            caller="eap_alarm_worker",
        )

        logger.info(
            "eap_alarm_worker: Oracle returned %d rows job_id=%s", len(df), job_id
        )

        # Decode AlarmCategory (EA-05) — apply at spool-write time
        if "ALARM_CATEGORY_CODE" in df.columns:
            df["ALARM_CATEGORY"] = df["ALARM_CATEGORY_CODE"].apply(decode_alarm_category)
        else:
            df["ALARM_CATEGORY"] = decode_alarm_category(None)

        # Add eqp_types_filter column for partition reuse validation (§3.17)
        df["eqp_types_filter"] = type_hash

        # Fetch DETAIL_PARAMS (extra EAV params, excluding AlarmText/AlarmCategory/AlarmCode)
        # Build per-event DETAIL_PARAMS JSON string
        try:
            detail_sql = _DETAIL_PARAMS_SQL_TEMPLATE.format(equipment_filter=equipment_filter)
            detail_df = read_sql_df_slow(
                detail_sql,
                params=params,
                timeout_seconds=EAP_ALARM_JOB_TIMEOUT_SECONDS,
                caller="eap_alarm_worker_detail",
            )

            if not detail_df.empty and "EVENT_ID" in detail_df.columns:
                # Build event_id → {param_name: param_value} map
                detail_map: Dict[str, Dict[str, str]] = {}
                for _, row in detail_df.iterrows():
                    eid = str(row["EVENT_ID"]) if row["EVENT_ID"] is not None else None
                    pname = str(row["PARAMETER_NAME"]) if row["PARAMETER_NAME"] is not None else None
                    pval = str(row["PARAMETER_VALUE"]) if row["PARAMETER_VALUE"] is not None else None
                    if eid and pname:
                        if eid not in detail_map:
                            detail_map[eid] = {}
                        detail_map[eid][pname] = pval

                df["DETAIL_PARAMS"] = df["EVENT_ID"].apply(
                    lambda eid: (
                        json.dumps(detail_map[str(eid)], ensure_ascii=False)
                        if eid is not None and str(eid) in detail_map and detail_map[str(eid)]
                        else None
                    )
                )
            else:
                df["DETAIL_PARAMS"] = None
        except Exception as detail_exc:
            logger.warning(
                "eap_alarm_worker: DETAIL_PARAMS fetch failed (job_id=%s): %s",
                job_id, detail_exc,
            )
            df["DETAIL_PARAMS"] = None

        # Ensure all 10 columns exist in correct order (§3.17)
        for col in _PARQUET_COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[_PARQUET_COLUMNS]

        # Write parquet (no pandas intermediary; use pyarrow directly)
        import pyarrow as pa
        import pyarrow.parquet as pq

        # Convert DataFrame types for parquet
        schema = pa.schema([
            pa.field("EVENT_ID", pa.string(), nullable=False),
            pa.field("EQP_ID", pa.string(), nullable=False),
            pa.field("EQP_TYPE", pa.string(), nullable=False),
            pa.field("LOT_ID", pa.string(), nullable=True),
            pa.field("ALARM_TEXT", pa.string(), nullable=True),
            pa.field("ALARM_CATEGORY_CODE", pa.float64(), nullable=True),
            pa.field("ALARM_CATEGORY", pa.string(), nullable=False),
            pa.field("ALARM_TIME", pa.timestamp("us"), nullable=False),
            pa.field("DETAIL_PARAMS", pa.string(), nullable=True),
            pa.field("eqp_types_filter", pa.string(), nullable=False),
        ])

        # Coerce EVENT_ID to string (it's a ROWID from Oracle)
        for str_col in ("EVENT_ID", "EQP_ID", "EQP_TYPE", "ALARM_CATEGORY", "eqp_types_filter"):
            df[str_col] = df[str_col].astype(str)

        table = pa.Table.from_pandas(df, schema=schema, safe=False)

        update_job_progress(_JOB_PREFIX, job_id, status="running", progress="writing parquet", pct="90")

        pq.write_table(table, spool_path, compression="snappy")
        row_count = len(df)

        logger.info(
            "eap_alarm_worker: parquet written path=%s rows=%d job_id=%s",
            spool_path, row_count, job_id,
        )

        # Register spool metadata in Redis
        try:
            from mes_dashboard.core.query_spool_store import register_spool_file
            from pathlib import Path
            register_spool_file(
                "eap_alarm",
                spool_key,
                Path(spool_path),
                row_count,
                ttl_seconds=EAP_ALARM_SPOOL_TTL,
            )
        except Exception as reg_exc:
            logger.warning(
                "eap_alarm_worker: spool registration failed job_id=%s: %s",
                job_id, reg_exc,
            )

        complete_job(_JOB_PREFIX, job_id, query_id=spool_key)
        update_job_progress(_JOB_PREFIX, job_id, status="complete", progress="done", pct="100")
        logger.info("eap_alarm_worker: job completed job_id=%s spool_key=%s", job_id, spool_key)

    except Exception as exc:
        logger.error(
            "eap_alarm_worker: job failed job_id=%s: %s", job_id, exc, exc_info=True
        )
        complete_job(_JOB_PREFIX, job_id, error=str(exc))
        raise


# ── Central job registry — must fire at import time ───────────────────────────
from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type  # noqa: E402

register_job_type(JobTypeConfig(
    job_type="eap-alarm",
    queue_name=EAP_ALARM_WORKER_QUEUE,
    worker_fn=run_eap_alarm_query_job,
    timeout_seconds=EAP_ALARM_JOB_TIMEOUT_SECONDS,
    ttl_seconds=EAP_ALARM_JOB_TTL_SECONDS,
))
