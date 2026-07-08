# -*- coding: utf-8 -*-
"""Unified event query fetcher with cache and domain-level policy metadata."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading
from collections import defaultdict
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any, Callable, Dict, List, Tuple

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

            # closing() guarantees the generator's finally block runs (releasing
            # the slow-query semaphore permit + slow-pool Oracle connection) even
            # when we break out early on the total-row guard. Without it those
            # resources only release at GC, progressively draining the slow pool
            # across consecutive queries and wedging query-tool ("卡住 after N queries").
            with closing(read_sql_df_slow_iter(sql, builder.params, timeout_seconds=60)) as row_iter:
                for columns, rows in row_iter:
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
                                    grouped[cid].append(enriched)  # noqa: F821
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
                        grouped[cid].append(record)  # noqa: F821
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
    def _stream_batches_to_writer(
        normalized_ids: List[str],
        domain: str,
        row_callback: Callable[[List[str], List[tuple]], None],
    ) -> Tuple[int, List]:
        """Stream Oracle query results to *row_callback* without a row guard.

        Extracts batch/threading/jobs-CONTAINERIDS expansion logic from
        ``fetch_events()``.  The callback receives ``(columns, rows)`` where
        *rows* is a list of raw tuples; for the ``jobs`` domain the CONTAINERID
        column is pre-expanded so each tuple corresponds to one (job, cid) pair.

        Returns ``(total_row_count, failures)`` where *failures* is a list of
        ``(batch_ids, exc)`` pairs for batches that raised exceptions.
        """
        spec = _DOMAIN_SPECS[domain]
        filter_column = spec["filter_column"]
        match_mode = spec.get("match_mode", "in")
        total_row_count = [0]

        def _process_batch(batch_ids: List[str]) -> None:
            builder = QueryBuilder()
            if match_mode == "contains":
                builder.add_or_like_conditions(filter_column, batch_ids, position="both")
            else:
                builder.add_in_condition(filter_column, batch_ids)
            sql = EventFetcher._build_domain_sql(domain, builder.get_conditions_sql())

            # closing() ensures the slow-query permit + Oracle connection release
            # deterministically even if row_callback raises mid-stream.
            with closing(read_sql_df_slow_iter(sql, builder.params, timeout_seconds=60)) as row_iter:
                for columns, rows in row_iter:
                    if not rows:
                        continue

                    if domain == "jobs":
                        try:
                            cids_idx = columns.index("CONTAINERIDS")
                            cid_idx = columns.index("CONTAINERID")
                        except ValueError:
                            row_callback(columns, list(rows))
                            total_row_count[0] += len(rows)
                            continue

                        expanded: List[tuple] = []
                        for row in rows:
                            containers_val = row[cids_idx]
                            if not isinstance(containers_val, str) or not containers_val:
                                continue
                            for cid in batch_ids:
                                if cid in containers_val:
                                    row_list = list(row)
                                    row_list[cid_idx] = cid
                                    expanded.append(tuple(row_list))

                        if expanded:
                            row_callback(columns, expanded)
                            total_row_count[0] += len(expanded)
                    else:
                        row_callback(columns, list(rows))
                        total_row_count[0] += len(rows)

        batches = [
            normalized_ids[i:i + ORACLE_IN_BATCH_SIZE]
            for i in range(0, len(normalized_ids), ORACLE_IN_BATCH_SIZE)
        ]

        if len(batches) <= 1:
            for batch in batches:
                _process_batch(batch)
            failures: List = []
        else:
            failures = []
            with ThreadPoolExecutor(max_workers=min(len(batches), EVENT_FETCHER_MAX_WORKERS)) as executor:
                futures = {executor.submit(_process_batch, b): b for b in batches}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        failures.append((futures[future], exc))
                        logger.error(
                            "EventFetcher._stream_batches_to_writer batch failed domain=%s batch_size=%s",
                            domain, len(futures[future]), exc_info=True,
                        )

        return total_row_count[0], failures

    @staticmethod
    def fetch_events_to_parquet(
        container_ids: List[str],
        domain: str,
        dest_path: "Any",
    ) -> Tuple[int, Dict[str, Any]]:
        """Fetch events for *domain* and stream them directly to a parquet file.

        True streaming path: Oracle cursor → ``read_sql_df_slow_iter`` →
        ``pyarrow.ParquetWriter``.  No row guard (EVENT_FETCHER_MAX_TOTAL_ROWS
        is NOT applied here — spool-safe path).

        Returns ``(row_count, quality_meta)``.  When there are no rows an empty
        parquet file is written so callers always have a valid file at *dest_path*.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq
        from pathlib import Path

        if domain not in _DOMAIN_SPECS:
            raise ValueError(f"Unsupported event domain: {domain}")

        normalized_ids = _normalize_ids(container_ids)
        dest_path = Path(str(dest_path))
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        if not normalized_ids:
            pq.write_table(pa.table({}), dest_path)
            return 0, build_quality_meta(
                status=QUALITY_STATUS_COMPLETE,
                scope=QUALITY_SCOPE_DOMAIN,
                domain=domain,
                observed_rows=0,
            )

        writer = None
        schema = None
        lock = threading.Lock()

        def _write_callback(columns: List[str], rows: List[tuple]) -> None:
            nonlocal writer, schema
            if not rows:
                return
            col_arrays = {
                col: [float(v) if isinstance(v, Decimal) else v for v in (row[i] for row in rows)]
                for i, col in enumerate(columns)
            }
            table = pa.table(col_arrays)
            with lock:
                if writer is None:
                    schema = table.schema
                    writer = pq.ParquetWriter(dest_path, schema)
                else:
                    try:
                        table = table.cast(schema, safe=False)
                    except Exception as cast_exc:
                        logger.debug(
                            "EventFetcher.fetch_events_to_parquet schema cast skipped domain=%s: %s",
                            domain, cast_exc,
                        )
                writer.write_table(table)

        try:
            row_count, failures = EventFetcher._stream_batches_to_writer(
                normalized_ids, domain, _write_callback
            )
        finally:
            if writer is not None:
                writer.close()

        if writer is None:
            # No rows written — create empty parquet so dest_path always exists
            pq.write_table(pa.table({}), dest_path)

        reasons: List[str] = []
        status = QUALITY_STATUS_COMPLETE
        failed_ranges: List[Dict[str, str]] = []
        partial_meta: Dict[str, Any] = {}

        if failures:
            status = QUALITY_STATUS_PARTIAL
            reasons.append("chunk_failure")
            for batch, _ in failures:
                if not batch:
                    continue
                failed_ranges.append({"start": str(batch[0]), "end": str(batch[-1])})
            partial_meta = build_partial_failure_meta(
                failed_count=len(failures),
                failed_ranges=failed_ranges,
            )

        quality_meta = build_quality_meta(
            status=status,
            scope=QUALITY_SCOPE_DOMAIN,
            domain=domain,
            reasons=reasons,
            observed_rows=row_count,
            failed_ranges=failed_ranges,
            extra={
                "has_partial_failure": partial_meta.get("has_partial_failure", False),
                "failed_chunk_count": partial_meta.get("failed_chunk_count", 0),
            } if partial_meta else None,
        )
        logger.info(
            "EventFetcher.fetch_events_to_parquet: domain=%s rows=%d path=%s",
            domain, row_count, dest_path,
        )
        return row_count, quality_meta
