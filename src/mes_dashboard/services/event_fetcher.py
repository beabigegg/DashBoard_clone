# -*- coding: utf-8 -*-
"""Unified event query fetcher with cache and domain-level policy metadata."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from mes_dashboard.core.cache import cache_get, cache_set
from mes_dashboard.core.partial_failure_contract import build_partial_failure_meta
from mes_dashboard.core.query_quality_contract import (
    QUALITY_SCOPE_DOMAIN,
    QUALITY_STATUS_COMPLETE,
    QUALITY_STATUS_PARTIAL,
    QUALITY_STATUS_TRUNCATED,
    build_event_fetch_result,
    build_quality_meta,
    unpack_event_fetch_result,
)
from mes_dashboard.core.database import read_sql_df_slow_iter
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.event_fetcher")

ORACLE_IN_BATCH_SIZE = 1000
EVENT_FETCHER_MAX_WORKERS = int(os.getenv('EVENT_FETCHER_MAX_WORKERS', '2'))
CACHE_SKIP_CID_THRESHOLD = int(os.getenv('EVENT_FETCHER_CACHE_SKIP_CID_THRESHOLD', '10000'))
EVENT_FETCHER_MAX_TOTAL_ROWS = int(os.getenv('EVENT_FETCHER_MAX_TOTAL_ROWS', '500000'))
EVENT_FETCHER_ALLOW_PARTIAL_RESULTS = (
    os.getenv('EVENT_FETCHER_ALLOW_PARTIAL_RESULTS', 'false').strip().lower()
    in {'1', 'true', 'yes', 'on'}
)

_DOMAIN_SPECS: Dict[str, Dict[str, Any]] = {
    "history": {
        "filter_column": "h.CONTAINERID",
        "cache_ttl": 300,
        "bucket": "event-history",
        "max_env": "EVT_HISTORY_RATE_MAX_REQUESTS",
        "window_env": "EVT_HISTORY_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "materials": {
        "filter_column": "m.CONTAINERID",
        "cache_ttl": 300,
        "schema_version": 2,
        "bucket": "event-materials",
        "max_env": "EVT_MATERIALS_RATE_MAX_REQUESTS",
        "window_env": "EVT_MATERIALS_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "rejects": {
        "filter_column": "r.CONTAINERID",
        "cache_ttl": 300,
        "schema_version": 2,
        "bucket": "event-rejects",
        "max_env": "EVT_REJECTS_RATE_MAX_REQUESTS",
        "window_env": "EVT_REJECTS_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "holds": {
        "filter_column": "h.CONTAINERID",
        "cache_ttl": 180,
        "schema_version": 2,
        "bucket": "event-holds",
        "max_env": "EVT_HOLDS_RATE_MAX_REQUESTS",
        "window_env": "EVT_HOLDS_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "jobs": {
        "filter_column": "j.CONTAINERIDS",
        "match_mode": "contains",
        "cache_ttl": 180,
        "bucket": "event-jobs",
        "max_env": "EVT_JOBS_RATE_MAX_REQUESTS",
        "window_env": "EVT_JOBS_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "upstream_history": {
        "filter_column": "h.CONTAINERID",
        "cache_ttl": 300,
        "bucket": "event-upstream",
        "max_env": "EVT_UPSTREAM_RATE_MAX_REQUESTS",
        "window_env": "EVT_UPSTREAM_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "downstream_rejects": {
        "filter_column": "r.CONTAINERID",
        "cache_ttl": 300,
        "bucket": "event-downstream-rejects",
        "max_env": "EVT_DOWNSTREAM_REJECTS_RATE_MAX_REQUESTS",
        "window_env": "EVT_DOWNSTREAM_REJECTS_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(default)
    return max(value, 1)


def _normalize_ids(container_ids: List[str]) -> List[str]:
    if not container_ids:
        return []
    seen = set()
    normalized: List[str] = []
    for cid in container_ids:
        if not isinstance(cid, str):
            continue
        value = cid.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


class EventFetcher:
    """Fetches container-scoped event records with cache and batching."""

    _CONTAINER_EQ_PARAM_PATTERN = re.compile(
        r"(?:[A-Za-z_][A-Za-z0-9_]*\.)?CONTAINERID\s*=\s*:container_id",
        re.IGNORECASE,
    )

    @staticmethod
    def _cache_key(domain: str, container_ids: List[str]) -> str:
        normalized = sorted(_normalize_ids(container_ids))
        digest = hashlib.md5("|".join(normalized).encode("utf-8")).hexdigest()[:12]
        schema_version = int(_DOMAIN_SPECS.get(domain, {}).get("schema_version", 1))
        return f"evt:{domain}:v{schema_version}:{digest}"

    @staticmethod
    def _replace_container_filter(sql: str, condition_sql: str) -> str:
        """Replace single-CID predicate with batched predicate in domain SQL."""
        replaced_sql, replacements = EventFetcher._CONTAINER_EQ_PARAM_PATTERN.subn(
            condition_sql,
            sql,
            count=1,
        )
        if replacements == 0:
            logger.warning(
                "EventFetcher container filter replacement missed target predicate"
            )
        return replaced_sql

    @staticmethod
    def _get_rate_limit_config(domain: str) -> Dict[str, int | str]:
        spec = _DOMAIN_SPECS.get(domain)
        if spec is None:
            raise ValueError(f"Unsupported event domain: {domain}")
        return {
            "bucket": spec["bucket"],
            "max_attempts": _env_int(spec["max_env"], spec["default_max"]),
            "window_seconds": _env_int(spec["window_env"], spec["default_window"]),
        }

    @staticmethod
    def _build_domain_sql(domain: str, condition_sql: str) -> str:
        if domain == "upstream_history":
            return SQLLoader.load_with_params(
                "mid_section_defect/upstream_history",
                ANCESTOR_FILTER=condition_sql,
            )

        if domain == "downstream_rejects":
            return SQLLoader.load_with_params(
                "mid_section_defect/downstream_rejects",
                DESCENDANT_FILTER=condition_sql,
            )

        if domain == "history":
            sql = SQLLoader.load("query_tool/lot_history")
            sql = EventFetcher._replace_container_filter(sql, condition_sql)
            return sql.replace("{{ WORKCENTER_FILTER }}", "")

        if domain == "materials":
            sql = SQLLoader.load("query_tool/lot_materials")
            return EventFetcher._replace_container_filter(sql, condition_sql)

        if domain == "rejects":
            sql = SQLLoader.load("query_tool/lot_rejects")
            return EventFetcher._replace_container_filter(sql, condition_sql)

        if domain == "holds":
            sql = SQLLoader.load("query_tool/lot_holds")
            return EventFetcher._replace_container_filter(sql, condition_sql)

        if domain == "jobs":
            return f"""
            SELECT
                j.JOBID,
                j.RESOURCEID,
                j.RESOURCENAME,
                j.JOBSTATUS,
                j.JOBMODELNAME,
                j.JOBORDERNAME,
                j.CREATEDATE,
                j.COMPLETEDATE,
                j.CAUSECODENAME,
                j.REPAIRCODENAME,
                j.SYMPTOMCODENAME,
                j.CONTAINERIDS,
                j.CONTAINERNAMES,
                NULL AS CONTAINERID
            FROM DWH.DW_MES_JOB j
            WHERE {condition_sql}
            ORDER BY j.CREATEDATE DESC
            """

        raise ValueError(f"Unsupported event domain: {domain}")

    @staticmethod
    def fetch_events(
        container_ids: List[str],
        domain: str,
    ) -> Dict[str, Any]:
        """Fetch event records grouped by CONTAINERID."""
        if domain not in _DOMAIN_SPECS:
            raise ValueError(f"Unsupported event domain: {domain}")

        normalized_ids = _normalize_ids(container_ids)
        if not normalized_ids:
            return build_event_fetch_result(
                {},
                build_quality_meta(
                    status=QUALITY_STATUS_COMPLETE,
                    scope=QUALITY_SCOPE_DOMAIN,
                    domain=domain,
                    observed_rows=0,
                ),
            )

        cache_key = EventFetcher._cache_key(domain, normalized_ids)
        cached = cache_get(cache_key)
        if cached is not None:
            cached_records, cached_meta = unpack_event_fetch_result(cached, domain=domain)
            return build_event_fetch_result(cached_records, cached_meta)

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        total_row_count = [0]  # mutable counter shared across batches
        truncated = [False]
        max_total_rows = EVENT_FETCHER_MAX_TOTAL_ROWS
        spec = _DOMAIN_SPECS[domain]
        filter_column = spec["filter_column"]
        match_mode = spec.get("match_mode", "in")

        def _sanitize_value(v):
            """Replace NaN float values with None for JSON-safe serialization."""
            if isinstance(v, float) and math.isnan(v):
                return None
            return v

        def _fetch_and_group_batch(batch_ids):
            """Fetch a batch using fetchmany iterator and group into ``grouped``."""
            if truncated[0]:
                return
            builder = QueryBuilder()
            if match_mode == "contains":
                builder.add_or_like_conditions(filter_column, batch_ids, position="both")
            else:
                builder.add_in_condition(filter_column, batch_ids)
            sql = EventFetcher._build_domain_sql(domain, builder.get_conditions_sql())

            for columns, rows in read_sql_df_slow_iter(sql, builder.params, timeout_seconds=60):
                if truncated[0]:
                    break
                for row in rows:
                    record = {k: _sanitize_value(v) for k, v in zip(columns, row)}
                    if domain == "jobs":
                        containers = record.get("CONTAINERIDS")
                        if not isinstance(containers, str) or not containers:
                            continue
                        for cid in batch_ids:
                            if cid in containers:
                                enriched = dict(record)
                                enriched["CONTAINERID"] = cid
                                grouped[cid].append(enriched)
                                total_row_count[0] += 1
                        if total_row_count[0] >= max_total_rows:
                            logger.warning(
                                "EventFetcher total-row guard triggered domain=%s rows=%s limit=%s — truncating",
                                domain, total_row_count[0], max_total_rows,
                            )
                            truncated[0] = True
                            break
                        continue
                    cid = record.get("CONTAINERID")
                    if not isinstance(cid, str) or not cid:
                        continue
                    grouped[cid].append(record)
                    total_row_count[0] += 1
                    if total_row_count[0] >= max_total_rows:
                        logger.warning(
                            "EventFetcher total-row guard triggered domain=%s rows=%s limit=%s — truncating",
                            domain, total_row_count[0], max_total_rows,
                        )
                        truncated[0] = True
                        break

        batches = [
            normalized_ids[i:i + ORACLE_IN_BATCH_SIZE]
            for i in range(0, len(normalized_ids), ORACLE_IN_BATCH_SIZE)
        ]

        if len(batches) <= 1:
            for batch in batches:
                _fetch_and_group_batch(batch)
            failures = []
        else:
            failures = []
            with ThreadPoolExecutor(max_workers=min(len(batches), EVENT_FETCHER_MAX_WORKERS)) as executor:
                futures = {executor.submit(_fetch_and_group_batch, b): b for b in batches}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        failures.append((futures[future], exc))
                        logger.error(
                            "EventFetcher batch query failed domain=%s batch_size=%s",
                            domain, len(futures[future]), exc_info=True,
                        )
            if failures and not EVENT_FETCHER_ALLOW_PARTIAL_RESULTS:
                failed_cids = sum(len(batch) for batch, _ in failures)
                raise RuntimeError(
                    f"EventFetcher chunk failed (domain={domain}, failed_chunks={len(failures)}, failed_cids={failed_cids})"
                )

        records_by_cid = dict(grouped)
        del grouped

        reasons: List[str] = []
        status = QUALITY_STATUS_COMPLETE
        failed_ranges: List[Dict[str, str]] = []
        partial_meta: Dict[str, Any] = {}

        if truncated[0]:
            status = QUALITY_STATUS_TRUNCATED
            reasons.append("max_total_rows_exceeded")

        if failures:
            status = QUALITY_STATUS_PARTIAL
            reasons.append("chunk_failure")
            for batch, _ in failures:
                if not batch:
                    continue
                failed_ranges.append({
                    "start": str(batch[0]),
                    "end": str(batch[-1]),
                })
            partial_meta = build_partial_failure_meta(
                failed_count=len(failures),
                failed_ranges=failed_ranges,
            )

        quality_meta = build_quality_meta(
            status=status,
            scope=QUALITY_SCOPE_DOMAIN,
            domain=domain,
            reasons=reasons,
            observed_rows=total_row_count[0],
            max_rows=max_total_rows if truncated[0] else None,
            failed_ranges=failed_ranges,
            extra={
                "has_partial_failure": partial_meta.get("has_partial_failure", False),
                "failed_chunk_count": partial_meta.get("failed_chunk_count", 0),
            } if partial_meta else None,
        )
        result = build_event_fetch_result(records_by_cid, quality_meta)

        if len(normalized_ids) <= CACHE_SKIP_CID_THRESHOLD:
            cache_set(cache_key, result, ttl=_DOMAIN_SPECS[domain]["cache_ttl"])
        else:
            logger.warning(
                "EventFetcher skipping cache domain=%s cid_count=%s (threshold=%s)",
                domain, len(normalized_ids), CACHE_SKIP_CID_THRESHOLD,
            )
        logger.info(
            "EventFetcher fetched domain=%s queried_cids=%s hit_cids=%s truncated=%s",
            domain,
            len(normalized_ids),
            len(records_by_cid),
            truncated[0],
        )
        return result

    @staticmethod
    def fetch_events_to_parquet(
        container_ids: List[str],
        domain: str,
        dest_path: "Any",
    ) -> int:
        """Fetch events for *domain* and write them directly to a parquet file.

        Task 6.3: spool-oriented stage output that avoids full in-memory
        materialisation.  Callers that have migrated to the unified spool
        pipeline can use this method to stream from Oracle → parquet without
        building a large Python dict structure.

        Returns the number of rows written.  The row truncation guard
        (EVENT_FETCHER_MAX_TOTAL_ROWS) remains active until this path
        replaces the legacy in-memory path for all callers (task 6.4).
        """
        import tempfile
        from pathlib import Path
        import pandas as pd

        # Use the existing in-memory path and then write to parquet.
        # A future optimization can replace this with true streaming via
        # pyarrow.parquet.ParquetWriter, but for now the guard-gated
        # in-memory path is preserved (task 6.4 / D7).
        result_payload = EventFetcher.fetch_events(container_ids, domain)
        records_by_cid, _quality_meta = unpack_event_fetch_result(result_payload, domain=domain)

        rows = []
        for records in records_by_cid.values():
            if isinstance(records, list):
                rows.extend(r for r in records if isinstance(r, dict))

        if not rows:
            df = pd.DataFrame()
        else:
            df = pd.DataFrame(rows)

        dest_path = Path(str(dest_path))
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(dest_path, engine="pyarrow", index=False)
        logger.info(
            "EventFetcher.fetch_events_to_parquet: domain=%s rows=%d path=%s",
            domain, len(df), dest_path,
        )
        return len(df)
