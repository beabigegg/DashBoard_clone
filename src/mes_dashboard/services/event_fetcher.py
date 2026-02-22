# -*- coding: utf-8 -*-
"""Unified event query fetcher with cache and domain-level policy metadata."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from collections import defaultdict
from typing import Any, Dict, List

from mes_dashboard.core.cache import cache_get, cache_set
from mes_dashboard.core.database import read_sql_df
from mes_dashboard.sql import QueryBuilder, SQLLoader

logger = logging.getLogger("mes_dashboard.event_fetcher")

ORACLE_IN_BATCH_SIZE = 1000

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
        "bucket": "event-materials",
        "max_env": "EVT_MATERIALS_RATE_MAX_REQUESTS",
        "window_env": "EVT_MATERIALS_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "rejects": {
        "filter_column": "CONTAINERID",
        "cache_ttl": 300,
        "bucket": "event-rejects",
        "max_env": "EVT_REJECTS_RATE_MAX_REQUESTS",
        "window_env": "EVT_REJECTS_RATE_WINDOW_SECONDS",
        "default_max": 20,
        "default_window": 60,
    },
    "holds": {
        "filter_column": "CONTAINERID",
        "cache_ttl": 180,
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
        return f"evt:{domain}:{digest}"

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
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Fetch event records grouped by CONTAINERID."""
        if domain not in _DOMAIN_SPECS:
            raise ValueError(f"Unsupported event domain: {domain}")

        normalized_ids = _normalize_ids(container_ids)
        if not normalized_ids:
            return {}

        cache_key = EventFetcher._cache_key(domain, normalized_ids)
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        spec = _DOMAIN_SPECS[domain]
        filter_column = spec["filter_column"]
        match_mode = spec.get("match_mode", "in")

        for i in range(0, len(normalized_ids), ORACLE_IN_BATCH_SIZE):
            batch = normalized_ids[i:i + ORACLE_IN_BATCH_SIZE]
            builder = QueryBuilder()
            if match_mode == "contains":
                builder.add_or_like_conditions(filter_column, batch, position="both")
            else:
                builder.add_in_condition(filter_column, batch)

            sql = EventFetcher._build_domain_sql(domain, builder.get_conditions_sql())
            df = read_sql_df(sql, builder.params)
            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                if domain == "jobs":
                    record = row.to_dict()
                    containers = record.get("CONTAINERIDS")
                    if not isinstance(containers, str) or not containers:
                        continue
                    for cid in batch:
                        if cid in containers:
                            enriched = dict(record)
                            enriched["CONTAINERID"] = cid
                            grouped[cid].append(enriched)
                    continue

                cid = row.get("CONTAINERID")
                if not isinstance(cid, str) or not cid:
                    continue
                grouped[cid].append(row.to_dict())

        result = dict(grouped)
        cache_set(cache_key, result, ttl=_DOMAIN_SPECS[domain]["cache_ttl"])
        logger.info(
            "EventFetcher fetched domain=%s queried_cids=%s hit_cids=%s",
            domain,
            len(normalized_ids),
            len(result),
        )
        return result
