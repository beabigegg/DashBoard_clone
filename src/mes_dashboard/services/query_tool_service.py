# -*- coding: utf-8 -*-
"""Query Tool Service.

Provides functions for batch tracing and equipment period queries:
- LOT resolution (LOT ID / Serial Number / Work Order → CONTAINERID)
- LOT production history and adjacent lots
- LOT associations (materials, rejects, holds, jobs)
- Equipment period queries (status hours, lots, materials, rejects, jobs)
- CSV export functionality

Architecture:
- All historical tables use CONTAINERID as primary key (NOT CONTAINERNAME)
- EQUIPMENTID = RESOURCEID (same ID system)
- Uses SQLLoader for SQL templates
- Uses QueryBuilder for dynamic conditions
"""

import csv
import hashlib
import io
import logging
import os
import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Generator, Iterable, Tuple

import pandas as pd

from mes_dashboard.core.database import read_sql_df
from mes_dashboard.sql import QueryBuilder, SQLLoader
from mes_dashboard.services.container_resolution_policy import (
    assess_resolution_result,
    normalize_input_values,
    validate_resolution_request,
    validate_resolution_result,
)
from mes_dashboard.core.interactive_memory_guard import process_rss_mb
from mes_dashboard.core.exceptions import (
    UserInputError,
    ResourceNotFoundError,
    QueryTimeoutError,
    DataContractError,
    InternalQueryError,
)
from mes_dashboard.core.query_quality_contract import unpack_event_fetch_result
from mes_dashboard.services.event_fetcher import EventFetcher
from mes_dashboard.services.query_tool_sql_runtime import (
    aggregate_partial_trackouts,
    _PARTIAL_KEY_COLS_4,
    _PARTIAL_KEY_COLS_3,
    _PARTIAL_NONKEY_COLS_LOT,
    _PARTIAL_NONKEY_COLS_ADJACENT,
)

try:
    from mes_dashboard.core.database import read_sql_df_slow
except ImportError:
    def read_sql_df_slow(sql: str, params: Optional[Dict[str, Any]] = None, timeout_seconds: int = 120):
        """Compatibility wrapper when read_sql_df_slow is unavailable."""
        return read_sql_df(sql, params)

logger = logging.getLogger('mes_dashboard.query_tool')

# Constants
BATCH_SIZE = 1000  # Oracle IN clause limit
MAX_DATE_RANGE_DAYS = 730  # 2 years
DEFAULT_TIME_WINDOW_HOURS = 168  # 1 week for better PJ_TYPE detection
ADJACENT_LOTS_COUNT = 3


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "true" if default else "false")).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


QUERY_TOOL_RSS_REJECT_MB = float(os.getenv('QUERY_TOOL_RSS_REJECT_MB', '1100'))
QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE = int(os.getenv('QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE', '200'))
QUERY_TOOL_DETAIL_MAX_PER_PAGE = int(os.getenv('QUERY_TOOL_DETAIL_MAX_PER_PAGE', '500'))
QUERY_TOOL_SPOOL_TTL_SECONDS = int(os.getenv('QUERY_TOOL_SPOOL_TTL_SECONDS', '300'))
QUERY_TOOL_REJECT_INCLUDE_EXCLUDED_SCRAP = _env_bool(
    "QUERY_TOOL_REJECT_INCLUDE_EXCLUDED_SCRAP",
    False,
)
QUERY_TOOL_REJECT_EXCLUDE_MATERIAL_SCRAP = _env_bool(
    "QUERY_TOOL_REJECT_EXCLUDE_MATERIAL_SCRAP",
    True,
)
QUERY_TOOL_REJECT_EXCLUDE_PB_DIODE = _env_bool(
    "QUERY_TOOL_REJECT_EXCLUDE_PB_DIODE",
    True,
)
QUERY_TOOL_SPOOL_NS_HISTORY_BATCH = "query_tool_history_batch"
QUERY_TOOL_SPOOL_NS_ASSOC_BATCH_PREFIX = "query_tool_assoc_batch"


def _fetch_domain_records(container_ids: List[str], domain: str) -> tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    payload = EventFetcher.fetch_events(container_ids, domain)
    return unpack_event_fetch_result(payload, domain=domain)


def _sanitize_page(value: Any) -> int:
    try:
        return max(int(value or 1), 1)
    except Exception:
        return 1


def _sanitize_per_page(value: Any) -> int:
    if value is None:
        return max(QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE, 1)
    try:
        per_page = int(value)
    except Exception:
        per_page = QUERY_TOOL_DETAIL_DEFAULT_PER_PAGE
    if per_page <= 0:
        return 0
    return min(max(per_page, 1), max(QUERY_TOOL_DETAIL_MAX_PER_PAGE, 1))


def _paginate_rows(rows: List[Dict[str, Any]], page: int, per_page: int) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    total = len(rows)
    if per_page <= 0:
        pagination = {
            "page": 1,
            "per_page": total or 0,
            "total": total,
            "total_pages": 1,
        }
        return rows, pagination

    total_pages = max(1, (total + per_page - 1) // per_page)
    current_page = max(1, min(page, total_pages))
    start = (current_page - 1) * per_page
    end = start + per_page
    pagination = {
        "page": current_page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }
    return rows[start:end], pagination


def _check_rss_guard(operation: str) -> None:
    """Reject request if current worker RSS exceeds safety threshold.

    Raises MemoryError with a user-facing 中文 message so the route layer
    can convert it to a 503 / error JSON.
    """
    rss = process_rss_mb()
    if rss is None:
        return  # fail-open if psutil unavailable
    if rss > QUERY_TOOL_RSS_REJECT_MB:
        logger.warning(
            "RSS guard rejected %s — rss_mb=%.1f limit_mb=%.0f",
            operation, rss, QUERY_TOOL_RSS_REJECT_MB,
        )
        raise MemoryError(
            f"目前服務記憶體負載較高（RSS {rss:.1f} MB），暫停{operation}以保護系統，"
            "請稍後再試或縮小查詢範圍"
        )


def _max_batch_container_ids() -> int:
    try:
        return max(int(os.getenv("QUERY_TOOL_MAX_CONTAINER_IDS", "200")), 1)
    except (TypeError, ValueError):
        return 200


def _build_query_tool_batch_query_id(domain: str, container_ids: List[str]) -> str:
    payload = {
        "fn": "query_tool_batch",
        "domain": str(domain or "").strip().lower(),
        "container_ids": sorted(_normalize_search_tokens(container_ids)),
    }
    try:
        from mes_dashboard.services.batch_query_engine import compute_query_hash
        return compute_query_hash(payload)
    except Exception:
        raw = repr(payload).encode("utf-8", errors="ignore")
        return hashlib.md5(raw).hexdigest()[:16]


def _query_tool_batch_namespace(domain: str) -> str:
    d = str(domain or "").strip().lower()
    if d == "history":
        return QUERY_TOOL_SPOOL_NS_HISTORY_BATCH
    return f"{QUERY_TOOL_SPOOL_NS_ASSOC_BATCH_PREFIX}_{d or 'unknown'}"


def _query_tool_reject_policy() -> Dict[str, bool]:
    return {
        "include_excluded_scrap": QUERY_TOOL_REJECT_INCLUDE_EXCLUDED_SCRAP,
        "exclude_material_scrap": QUERY_TOOL_REJECT_EXCLUDE_MATERIAL_SCRAP,
        "exclude_pb_diode": QUERY_TOOL_REJECT_EXCLUDE_PB_DIODE,
    }


def _store_query_tool_batch_spool(
    *,
    namespace: str,
    query_id: str,
    rows: List[Dict[str, Any]],
) -> bool:
    if not rows:
        return False
    try:
        from mes_dashboard.core.query_spool_store import store_spooled_df
        df = pd.DataFrame(rows)
        if df.empty:
            return False
        return bool(
            store_spooled_df(
                namespace,
                query_id,
                df,
                ttl_seconds=max(QUERY_TOOL_SPOOL_TTL_SECONDS, 60),
            )
        )
    except Exception as exc:
        logger.debug(
            "query_tool spool store skipped namespace=%s query_id=%s: %s",
            namespace,
            query_id,
            exc,
        )
        return False


def _try_query_tool_spool_page(
    *,
    namespace: str,
    query_id: str,
    page: int,
    per_page: int,
    workcenter_names: Optional[List[str]] = None,
    reject_policy: Optional[Dict[str, bool]] = None,
) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    try:
        from mes_dashboard.services.query_tool_sql_runtime import (
            try_compute_page_from_spool,
        )
        return try_compute_page_from_spool(
            namespace=namespace,
            query_id=query_id,
            page=page,
            per_page=per_page,
            workcenter_names=workcenter_names,
            reject_policy=reject_policy,
        )
    except Exception as exc:
        logger.debug(
            "query_tool spool runtime unavailable namespace=%s query_id=%s: %s",
            namespace,
            query_id,
            exc,
        )
        return None, {"view_sql_fallback_reason": "query_tool_sql_runtime_unavailable"}


# ============================================================
# Validation Functions
# ============================================================

def validate_date_range(start_date: str, end_date: str, max_days: int = MAX_DATE_RANGE_DAYS) -> Optional[str]:
    """Validate date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        max_days: Maximum allowed days

    Returns:
        Error message if validation fails, None if valid.
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')

        if end < start:
            return '結束日期不可早於起始日期'

        diff = (end - start).days
        if diff > max_days:
            return f'日期範圍不可超過 {max_days} 天'

        return None
    except ValueError as e:
        return f'日期格式錯誤: {e}'


def validate_lot_input(input_type: str, values: List[str]) -> Optional[str]:
    """Validate LOT input based on type.

    Args:
        input_type: Type of input
        values: List of input values

    Returns:
        Error message if validation fails, None if valid.
    """
    return validate_resolution_request(input_type, values)


def validate_equipment_input(equipment_ids: List[str]) -> Optional[str]:
    """Validate equipment input.

    Args:
        equipment_ids: List of equipment IDs

    Returns:
        Error message if validation fails, None if valid.
    """
    if not equipment_ids:
        return '請選擇至少一台設備'

    return None


def _df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert DataFrame to list of records with proper type handling.

    Args:
        df: DataFrame to convert

    Returns:
        List of dictionaries
    """
    if df is None or df.empty:
        return []

    data = []
    for _, row in df.iterrows():
        record = {}
        for col in df.columns:
            value = row[col]
            if pd.isna(value):
                record[col] = None
            elif isinstance(value, datetime):
                record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, pd.Timestamp):
                record[col] = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, Decimal):
                record[col] = float(value)
            else:
                record[col] = value
        data.append(record)

    return data


def _normalize_search_tokens(values: Iterable[str]) -> List[str]:
    """Normalize user-provided search tokens while preserving order."""
    normalized: List[str] = []
    seen = set()
    for raw in values or []:
        token = str(raw or '').strip()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(token)
    return normalized


def _normalize_wildcard_token(value: str) -> str:
    """Normalize user wildcard syntax.

    Supports both SQL wildcard (`%`) and shell-style wildcard (`*`).
    """
    return str(value or '').replace('*', '%')


def _is_pattern_token(value: str) -> bool:
    token = _normalize_wildcard_token(value)
    return '%' in token or '_' in token


def _to_like_regex(pattern: str, *, case_insensitive: bool = False) -> re.Pattern:
    """Convert SQL LIKE pattern (`%`, `_`, `\\` escape) to Python regex."""
    token = _normalize_wildcard_token(pattern)
    parts: List[str] = ['^']
    i = 0
    while i < len(token):
        ch = token[i]
        if ch == '\\':
            # Keep Oracle ESCAPE semantics: \% or \_ means literal.
            if i + 1 < len(token):
                i += 1
                parts.append(re.escape(token[i]))
            else:
                parts.append(re.escape(ch))
        elif ch == '%':
            parts.append('.*')
        elif ch == '_':
            parts.append('.')
        else:
            parts.append(re.escape(ch))
        i += 1
    parts.append('$')
    flags = re.IGNORECASE if case_insensitive else 0
    return re.compile(''.join(parts), flags)


def _add_exact_or_pattern_condition(
    builder: QueryBuilder,
    column: str,
    values: List[str],
    *,
    case_insensitive: bool = False,
) -> None:
    """Add a single OR-group condition supporting exact and wildcard tokens."""
    tokens = _normalize_search_tokens(values)
    if not tokens:
        return

    col_expr = f"UPPER(NVL({column}, ''))" if case_insensitive else f"NVL({column}, '')"
    conditions: List[str] = []

    exact_tokens = [token for token in tokens if not _is_pattern_token(token)]
    pattern_tokens = [token for token in tokens if _is_pattern_token(token)]

    if exact_tokens:
        placeholders: List[str] = []
        for token in exact_tokens:
            param = builder._next_param()
            placeholders.append(f":{param}")
            builder.params[param] = token.upper() if case_insensitive else token
        conditions.append(f"{col_expr} IN ({', '.join(placeholders)})")

    for token in pattern_tokens:
        param = builder._next_param()
        normalized = _normalize_wildcard_token(token)
        builder.params[param] = normalized.upper() if case_insensitive else normalized
        conditions.append(f"{col_expr} LIKE :{param} ESCAPE '\\'")

    if conditions:
        builder.add_condition(f"({' OR '.join(conditions)})")


def _match_rows_by_tokens(
    tokens: List[str],
    rows: List[Dict[str, Any]],
    *,
    row_key: str,
    case_insensitive: bool = False,
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, int]]:
    """Map query tokens to matching rows and report not-found tokens."""
    normalized_tokens = _normalize_search_tokens(tokens)
    if not normalized_tokens:
        return [], [], {}

    def normalize_text(value: Any) -> str:
        text = str(value or '').strip()
        return text.upper() if case_insensitive else text

    row_pairs: List[Tuple[str, Dict[str, Any]]] = [
        (normalize_text(row.get(row_key)), row)
        for row in rows
        if normalize_text(row.get(row_key))
    ]

    exact_index: Dict[str, List[Dict[str, Any]]] = {}
    for key, row in row_pairs:
        exact_index.setdefault(key, []).append(row)

    matches: List[Dict[str, Any]] = []
    not_found: List[str] = []
    expansion_info: Dict[str, int] = {}
    seen_pairs = set()

    for token in normalized_tokens:
        token_key = normalize_text(token)
        matched_rows: List[Dict[str, Any]]

        if _is_pattern_token(token):
            regex = _to_like_regex(token, case_insensitive=case_insensitive)
            matched_rows = [
                row
                for value, row in row_pairs
                if regex.fullmatch(value)
            ]
        else:
            matched_rows = exact_index.get(token_key, [])

        if not matched_rows:
            not_found.append(token)
            continue

        expansion_info[token] = len(matched_rows)
        for row in matched_rows:
            cid = str(row.get('CONTAINERID') or row.get('container_id') or '').strip()
            dedup_key = (token, cid)
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)
            item = dict(row)
            item['input_value'] = token
            matches.append(item)

    return matches, not_found, expansion_info


# ============================================================
# LOT Resolution Functions
# ============================================================

def resolve_lots(input_type: str, values: List[str]) -> Dict[str, Any]:
    """Resolve input to CONTAINERID list.

    All historical tables (LOTWIPHISTORY, LOTMATERIALSHISTORY, etc.)
    use CONTAINERID as primary key, NOT CONTAINERNAME.
    This function converts user input to CONTAINERID for subsequent queries.

    Args:
        input_type: Type of input
        values: List of input values

    Returns:
        Dict with 'data' (list of {container_id, input_value}),
        'total', 'input_count', or 'error'.
    """
    # Validate input
    validation_error = validate_lot_input(input_type, values)
    if validation_error:
        raise UserInputError(validation_error)

    # Clean values
    cleaned = normalize_input_values(values)
    if not cleaned:
        raise UserInputError('請輸入有效的查詢條件')

    try:
        if input_type == 'lot_id':
            result = _resolve_by_lot_id(cleaned)
        elif input_type == 'wafer_lot':
            result = _resolve_by_wafer_lot(cleaned)
        elif input_type == 'gd_lot_id':
            result = _resolve_by_gd_lot_id(cleaned)
        elif input_type == 'serial_number':
            result = _resolve_by_serial_number(cleaned)
        elif input_type == 'work_order':
            result = _resolve_by_work_order(cleaned)
        elif input_type == 'gd_work_order':
            result = _resolve_by_gd_work_order(cleaned)
        else:
            raise UserInputError(f'不支援的輸入類型: {input_type}')

        guard_assessment = assess_resolution_result(result)
        overflow_tokens = guard_assessment.get("expansion_offenders") or []
        overflow_total = bool(guard_assessment.get("over_container_limit"))
        if overflow_tokens or overflow_total:
            logger.warning(
                "Resolution guardrail overflow (input_type=%s, offenders=%s, resolved=%s, max=%s); continuing with decompose path",
                input_type,
                len(overflow_tokens),
                guard_assessment.get("resolved_container_ids"),
                guard_assessment.get("max_container_ids"),
            )
            result["guardrail"] = {
                "overflow": True,
                "expansion_offenders": overflow_tokens,
                "resolved_container_ids": guard_assessment.get("resolved_container_ids"),
                "max_container_ids": guard_assessment.get("max_container_ids"),
            }
        # Keep compatibility: validation API remains available for strict call sites.
        guard_error = validate_resolution_result(result, strict=False)
        if guard_error:
            raise UserInputError(guard_error)
        return result

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT resolution failed: {exc}")
        raise InternalQueryError('解析失敗', cause=exc)


def _resolve_by_lot_id(lot_ids: List[str]) -> Dict[str, Any]:
    """Resolve LOT IDs (CONTAINERNAME) to CONTAINERID.

    Args:
        lot_ids: List of LOT IDs (CONTAINERNAME values)

    Returns:
        Resolution result dict.
    """
    builder = QueryBuilder()
    _add_exact_or_pattern_condition(builder, "CONTAINERNAME", lot_ids)
    sql = SQLLoader.load_with_params(
        "query_tool/lot_resolve_id",
        CONTAINER_FILTER=builder.get_conditions_sql(),
    )

    df = read_sql_df_slow(sql, builder.params, caller="query_tool:lot_resolve_id")
    data = _df_to_records(df)
    matched, not_found, expansion_info = _match_rows_by_tokens(
        lot_ids,
        data,
        row_key='CONTAINERNAME',
    )

    results = []
    for row in matched:
        results.append({
            'container_id': row.get('CONTAINERID'),
            'lot_id': row.get('CONTAINERNAME'),
            'input_value': row.get('input_value'),
            'spec_name': row.get('SPECNAME'),
            'qty': row.get('QTY'),
        })

    logger.info(f"LOT ID resolution: {len(results)} found, {len(not_found)} not found")

    return {
        'data': results,
        'total': len(results),
        'input_count': len(lot_ids),
        'not_found': not_found,
        'expansion_info': expansion_info,
    }


def _resolve_by_wafer_lot(wafer_lots: List[str]) -> Dict[str, Any]:
    """Resolve wafer lot values (FIRSTNAME) to CONTAINERID."""
    builder = QueryBuilder()
    _add_exact_or_pattern_condition(builder, "FIRSTNAME", wafer_lots)
    builder.add_condition("OBJECTTYPE = 'LOT'")
    sql = SQLLoader.load_with_params(
        "query_tool/lot_resolve_wafer_lot",
        WAFER_FILTER=builder.get_conditions_sql(),
    )

    df = read_sql_df_slow(sql, builder.params)
    data = _df_to_records(df)
    matched, not_found, expansion_info = _match_rows_by_tokens(
        wafer_lots,
        data,
        row_key='FIRSTNAME',
    )

    results = []
    for row in matched:
        cid = row.get('CONTAINERID')
        if not cid:
            continue
        results.append({
            'container_id': cid,
            'lot_id': row.get('CONTAINERNAME'),
            'input_value': row.get('input_value'),
            'spec_name': row.get('SPECNAME'),
            'qty': row.get('QTY'),
        })

    logger.info(f"Wafer lot resolution: {len(results)} containers from {len(wafer_lots)} wafer lots")
    return {
        'data': results,
        'total': len(results),
        'input_count': len(wafer_lots),
        'not_found': not_found,
        'expansion_info': expansion_info,
    }


def _is_gd_like(value: str) -> bool:
    text = str(value or '').strip().upper()
    return text.startswith('GD')


def _literal_prefix_before_wildcard(value: str) -> str:
    token = _normalize_wildcard_token(value)
    for idx, ch in enumerate(token):
        if ch in ('%', '_'):
            return token[:idx]
    return token


def _resolve_by_gd_lot_id(gd_lot_ids: List[str]) -> Dict[str, Any]:
    """Resolve GD lot IDs to CONTAINERID with strict GD validation."""
    invalid = [value for value in gd_lot_ids if not _is_gd_like(_literal_prefix_before_wildcard(value))]
    if invalid:
        raise UserInputError(f'GD LOT ID 格式錯誤: {", ".join(invalid)}')

    builder = QueryBuilder()
    _add_exact_or_pattern_condition(builder, "CONTAINERNAME", gd_lot_ids, case_insensitive=True)
    builder.add_condition("(UPPER(NVL(CONTAINERNAME, '')) LIKE 'GD%' OR UPPER(NVL(MFGORDERNAME, '')) LIKE 'GD%')")
    sql = SQLLoader.load_with_params(
        "query_tool/lot_resolve_id",
        CONTAINER_FILTER=builder.get_conditions_sql(),
    )

    df = read_sql_df_slow(sql, builder.params, caller="query_tool:lot_resolve_id")
    data = _df_to_records(df)
    matched, not_found, expansion_info = _match_rows_by_tokens(
        gd_lot_ids,
        data,
        row_key='CONTAINERNAME',
        case_insensitive=True,
    )

    results = []
    for row in matched:
        results.append({
            'container_id': row.get('CONTAINERID'),
            'lot_id': row.get('CONTAINERNAME'),
            'input_value': row.get('input_value'),
            'spec_name': row.get('SPECNAME'),
            'qty': row.get('QTY'),
        })

    logger.info(f"GD lot resolution: {len(results)} found, {len(not_found)} not found")
    return {
        'data': results,
        'total': len(results),
        'input_count': len(gd_lot_ids),
        'not_found': not_found,
        'expansion_info': expansion_info,
    }


def _resolve_by_serial_number(serial_numbers: List[str]) -> Dict[str, Any]:
    """Resolve serial-related inputs to CONTAINERID.

    Matching sources (in priority order):
      1. DW_MES_PJ_COMBINEDASSYLOTS.FINISHEDNAME (new serial path)
      2. DW_MES_CONTAINER.CONTAINERNAME (old serial / lot-id style inputs)
      3. DW_MES_CONTAINER.FIRSTNAME (bridge from serial to related lots)
    """
    tokens = _normalize_search_tokens(serial_numbers)
    if not tokens:
        return {
            'data': [],
            'total': 0,
            'input_count': 0,
            'not_found': [],
            'expansion_info': {},
        }

    source_configs = [
        {
            'name': 'finished_name',
            'priority': 0,
            'sql_name': 'query_tool/lot_resolve_serial',
            'filter_key': 'SERIAL_FILTER',
            'filter_column': 'p.FINISHEDNAME',
            'match_key': 'FINISHEDNAME',
            'extra_conditions': [],
        },
        {
            'name': 'container_name',
            'priority': 1,
            'sql_name': 'query_tool/lot_resolve_id',
            'filter_key': 'CONTAINER_FILTER',
            'filter_column': 'CONTAINERNAME',
            'match_key': 'CONTAINERNAME',
            'extra_conditions': ["OBJECTTYPE = 'LOT'"],
        },
        {
            'name': 'first_name',
            'priority': 2,
            'sql_name': 'query_tool/lot_resolve_wafer_lot',
            'filter_key': 'WAFER_FILTER',
            'filter_column': 'FIRSTNAME',
            'match_key': 'FIRSTNAME',
            'extra_conditions': ["OBJECTTYPE = 'LOT'"],
        },
    ]

    best_match_by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for config in source_configs:
        builder = QueryBuilder()
        _add_exact_or_pattern_condition(builder, config['filter_column'], tokens)
        for cond in config['extra_conditions']:
            builder.add_condition(cond)

        if not builder.conditions:
            continue

        sql = SQLLoader.load_with_params(
            config['sql_name'],
            **{config['filter_key']: builder.get_conditions_sql()},
        )
        df = read_sql_df_slow(sql, builder.params, caller=f"query_tool:{config['sql_name']}")
        data = _df_to_records(df)
        matched, _, _ = _match_rows_by_tokens(
            tokens,
            data,
            row_key=config['match_key'],
        )

        for row in matched:
            input_value = str(row.get('input_value') or '').strip()
            cid = str(row.get('CONTAINERID') or '').strip()
            if not input_value or not cid:
                continue

            candidate = {
                'container_id': cid,
                'lot_id': row.get('CONTAINERNAME') or cid,
                'input_value': input_value,
                'spec_name': row.get('SPECNAME'),
                'match_source': config['name'],
                '_priority': config['priority'],
            }
            key = (input_value, cid)
            existing = best_match_by_key.get(key)
            if existing is None or candidate['_priority'] < existing['_priority']:
                best_match_by_key[key] = candidate

    grouped_by_input: Dict[str, List[Dict[str, Any]]] = {}
    for item in best_match_by_key.values():
        grouped_by_input.setdefault(item['input_value'], []).append(item)

    results: List[Dict[str, Any]] = []
    not_found: List[str] = []
    expansion_info: Dict[str, int] = {}

    for token in tokens:
        rows = grouped_by_input.get(token, [])
        rows.sort(key=lambda row: (row.get('_priority', 999), str(row.get('lot_id') or '')))
        if not rows:
            not_found.append(token)
            continue

        expansion_info[token] = len(rows)
        for row in rows:
            row.pop('_priority', None)
            results.append(row)

    logger.info(
        "Serial number resolution: %s containers from %s inputs (not_found=%s)",
        len(results),
        len(tokens),
        len(not_found),
    )

    return {
        'data': results,
        'total': len(results),
        'input_count': len(tokens),
        'not_found': not_found,
        'expansion_info': expansion_info,
    }


def _resolve_by_work_order(work_orders: List[str]) -> Dict[str, Any]:
    """Resolve work orders (MFGORDERNAME) to CONTAINERID.

    Note: One work order may expand to many CONTAINERIDs (can be 100+).

    Args:
        work_orders: List of work orders

    Returns:
        Resolution result dict.
    """
    invalid = [value for value in work_orders if _is_gd_like(_literal_prefix_before_wildcard(value))]
    if invalid:
        raise UserInputError(f'正向工單僅支援 GA/GC，請改用反向 GD 工單查詢: {", ".join(invalid)}')

    builder = QueryBuilder()
    _add_exact_or_pattern_condition(builder, "MFGORDERNAME", work_orders, case_insensitive=True)
    builder.add_condition("(UPPER(NVL(MFGORDERNAME, '')) LIKE 'GA%' OR UPPER(NVL(MFGORDERNAME, '')) LIKE 'GC%')")
    sql = SQLLoader.load_with_params(
        "query_tool/lot_resolve_work_order",
        WORK_ORDER_FILTER=builder.get_conditions_sql(),
    )

    df = read_sql_df_slow(sql, builder.params, caller="query_tool:lot_resolve_work_order")
    data = _df_to_records(df)
    matched, not_found, expansion_info = _match_rows_by_tokens(
        work_orders,
        data,
        row_key='MFGORDERNAME',
        case_insensitive=True,
    )

    results = []
    for row in matched:
        results.append({
            'container_id': row.get('CONTAINERID'),
            'lot_id': row.get('CONTAINERNAME'),
            'input_value': row.get('input_value'),
            'spec_name': row.get('SPECNAME'),
        })

    logger.info(f"Work order resolution: {len(results)} containers from {len(work_orders)} orders")

    return {
        'data': results,
        'total': len(results),
        'input_count': len(work_orders),
        'not_found': not_found,
        'expansion_info': expansion_info,
    }


def _resolve_by_gd_work_order(work_orders: List[str]) -> Dict[str, Any]:
    """Resolve GD work orders to CONTAINERID."""
    invalid = [value for value in work_orders if not _is_gd_like(_literal_prefix_before_wildcard(value))]
    if invalid:
        raise UserInputError(f'GD 工單格式錯誤: {", ".join(invalid)}')

    builder = QueryBuilder()
    _add_exact_or_pattern_condition(builder, "MFGORDERNAME", work_orders, case_insensitive=True)
    builder.add_condition("UPPER(NVL(MFGORDERNAME, '')) LIKE 'GD%'")
    sql = SQLLoader.load_with_params(
        "query_tool/lot_resolve_work_order",
        WORK_ORDER_FILTER=builder.get_conditions_sql(),
    )

    df = read_sql_df_slow(sql, builder.params, caller="query_tool:lot_resolve_work_order")
    data = _df_to_records(df)
    matched, not_found, expansion_info = _match_rows_by_tokens(
        work_orders,
        data,
        row_key='MFGORDERNAME',
        case_insensitive=True,
    )

    results = []
    for row in matched:
        cid = row.get('CONTAINERID')
        if not cid:
            continue
        results.append({
            'container_id': cid,
            'lot_id': row.get('CONTAINERNAME'),
            'input_value': row.get('input_value'),
            'spec_name': row.get('SPECNAME'),
        })

    logger.info(f"GD work order resolution: {len(results)} containers from {len(work_orders)} orders")
    return {
        'data': results,
        'total': len(results),
        'input_count': len(work_orders),
        'not_found': not_found,
        'expansion_info': expansion_info,
    }


# ============================================================
# LOT History Functions
# ============================================================

def _get_workcenters_for_groups(groups: List[str]) -> List[str]:
    """Get workcenter names for given groups using filter_cache.

    Args:
        groups: List of WORKCENTER_GROUP names

    Returns:
        List of WORKCENTERNAME values
    """
    from mes_dashboard.services.filter_cache import get_workcenters_for_groups
    return get_workcenters_for_groups(groups)


def _enrich_workcenter_group(rows: list) -> list:
    """Add WORKCENTER_GROUP field to each history row based on WORKCENTERNAME.

    Uses filter_cache mapping first, then fallback pattern mapping.
    """
    from mes_dashboard.config.workcenter_groups import get_workcenter_group
    from mes_dashboard.services.filter_cache import (
        get_spec_workcenter_mapping,
        get_workcenter_mapping,
    )

    mapping = get_workcenter_mapping() or {}
    spec_mapping = get_spec_workcenter_mapping() or {}
    for row in rows:
        current_group = str(row.get('WORKCENTER_GROUP') or '').strip()
        if current_group:
            row['WORKCENTER_GROUP'] = current_group
            continue

        wc_name = str(row.get('WORKCENTERNAME') or '').strip()
        group_name = ""
        if wc_name and wc_name in mapping:
            group_name = str(mapping[wc_name].get('group') or '').strip()

        if not group_name and wc_name:
            group_name, _ = get_workcenter_group(wc_name)
            group_name = str(group_name or '').strip()

        if not group_name:
            spec_name = str(row.get('SPECNAME') or row.get('SPEC') or '').strip().upper()
            if spec_name and spec_name in spec_mapping:
                group_name = str(spec_mapping[spec_name].get('group') or '').strip()

        row['WORKCENTER_GROUP'] = group_name or wc_name or ''
    return rows


def _apply_query_tool_reject_policy(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply reject-history default policy filters to query-tool reject rows."""
    if not rows:
        return []

    df = pd.DataFrame(rows)
    if df.empty:
        return []

    mask = pd.Series(True, index=df.index)
    policy = _query_tool_reject_policy()

    if policy["exclude_material_scrap"] and "SCRAP_OBJECTTYPE" in df.columns:
        obj_type = df["SCRAP_OBJECTTYPE"].fillna("").astype(str).str.strip().str.upper()
        mask &= obj_type != "MATERIAL"

    if policy["exclude_pb_diode"] and "PRODUCTLINENAME" in df.columns:
        product = df["PRODUCTLINENAME"].fillna("").astype(str).str.strip().str.upper()
        mask &= ~product.str.match(r"^PB_")

    if not policy["include_excluded_scrap"]:
        excluded = set()
        try:
            from mes_dashboard.services.scrap_reason_exclusion_cache import (
                get_excluded_reasons,
            )

            excluded = {
                str(v or "").strip().upper()
                for v in (get_excluded_reasons() or set())
                if str(v or "").strip()
            }
        except Exception:
            excluded = set()

        if excluded and "LOSSREASON_CODE" in df.columns:
            code_upper = df["LOSSREASON_CODE"].fillna("").astype(str).str.strip().str.upper()
            mask &= ~code_upper.isin(excluded)
        if excluded and "LOSSREASONNAME" in df.columns:
            name_upper = df["LOSSREASONNAME"].fillna("").astype(str).str.strip().str.upper()
            mask &= ~name_upper.isin(excluded)

        if "LOSSREASONNAME" in df.columns:
            reason = df["LOSSREASONNAME"].fillna("").astype(str).str.strip().str.upper()
            mask &= reason.str.match(r"^[0-9]{3}_")
            mask &= ~reason.str.match(r"^(XXX|ZZZ)_")

    filtered = df[mask]
    return _df_to_records(filtered)


def get_lot_history(
    container_id: str,
    workcenter_groups: Optional[List[str]] = None,
    *,
    page: int = 1,
    per_page: int = 0,
) -> Dict[str, Any]:
    """Get production history for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)
        workcenter_groups: Optional list of WORKCENTER_GROUP names to filter by
        page: Page number (1-based)
        per_page: Records per page (0 = no pagination)

    Returns:
        Dict with 'data', 'total', 'pagination', 'quality_meta', or 'error'.
    """
    if not container_id:
        raise UserInputError('請指定 CONTAINERID')

    try:
        _check_rss_guard("LOT 生產履歷查詢")
        events_by_cid, quality_meta = _fetch_domain_records([container_id], "history")
        rows = list(events_by_cid.get(container_id, []))

        # Aggregate partial trackouts (QT-05/QT-06 strict guard)
        if rows:
            _agg_df = aggregate_partial_trackouts(
                pd.DataFrame(rows),
                _PARTIAL_KEY_COLS_4,
                _PARTIAL_NONKEY_COLS_LOT,
                query_id=container_id,
            )
            rows = _agg_df.to_dict(orient='records')

        if workcenter_groups:
            workcenters = _get_workcenters_for_groups(workcenter_groups)
            if workcenters:
                workcenter_set = set(workcenters)
                rows = [
                    row
                    for row in rows
                    if row.get('WORKCENTERNAME') in workcenter_set
                ]
                logger.debug(
                    f"Filtering by {len(workcenter_groups)} groups "
                    f"({len(workcenters)} workcenters)"
                )

        paged_rows, pagination = _paginate_rows(
            rows,
            _sanitize_page(page),
            _sanitize_per_page(per_page),
        )

        _enrich_workcenter_group(paged_rows)
        data = _df_to_records(pd.DataFrame(paged_rows))

        logger.debug(f"LOT history: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(rows),
            'container_id': container_id,
            'filtered_by_groups': workcenter_groups or [],
            'pagination': pagination,
            'quality_meta': quality_meta,
        }

    except MemoryError:
        raise
    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT history query failed for {container_id}: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_adjacent_lots(
    equipment_id: str,
    target_trackin_time: str,
    time_window_hours: int = DEFAULT_TIME_WINDOW_HOURS
) -> Dict[str, Any]:
    """Get adjacent lots (前後批) for a specific equipment.

    Finds lots processed before and after the target lot on the same equipment.
    Searches until finding a different PJ_TYPE, with minimum 3 lots in each direction.

    Args:
        equipment_id: Target equipment ID
        target_trackin_time: Target lot's TRACKINTIMESTAMP (ISO format)
        time_window_hours: Time window in hours (default 24)

    Returns:
        Dict with 'data' (adjacent lots with relative_position) and metadata.
    """
    if not all([equipment_id, target_trackin_time]):
        raise UserInputError('請指定設備和目標時間')

    try:
        # Parse target time
        if isinstance(target_trackin_time, str):
            target_time = datetime.strptime(target_trackin_time, '%Y-%m-%d %H:%M:%S')
        else:
            target_time = target_trackin_time

        sql = SQLLoader.load("query_tool/adjacent_lots")
        params = {
            'equipment_id': equipment_id,
            'target_trackin_time': target_time,
            'time_window_hours': time_window_hours,
        }

        df = read_sql_df_slow(sql, params)
        # Aggregate partial trackouts using 3-tuple key (QT-05/QT-06 strict guard)
        df = aggregate_partial_trackouts(
            df,
            _PARTIAL_KEY_COLS_3,
            _PARTIAL_NONKEY_COLS_ADJACENT,
            query_id=f"adjacent:{equipment_id}",
        )
        data = _df_to_records(df)

        logger.debug(f"Adjacent lots: {len(data)} records for {equipment_id}")

        return {
            'data': data,
            'total': len(data),
            'equipment_id': equipment_id,
            'target_time': target_trackin_time,
            'time_window_hours': time_window_hours,
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"Adjacent lots query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


# ============================================================
# LOT Batch Query Functions
# ============================================================

def get_lot_history_batch(
    container_ids: List[str],
    workcenter_groups: Optional[List[str]] = None,
    *,
    page: int = 1,
    per_page: int = 0,
) -> Dict[str, Any]:
    """Get production history for multiple LOTs in a single EventFetcher call.

    Args:
        container_ids: List of CONTAINERIDs (16-char hex)
        workcenter_groups: Optional list of WORKCENTER_GROUP names to filter by

    Returns:
        Dict with 'data' (merged history records) and 'total'.
    """
    if not container_ids:
        raise UserInputError('請指定 CONTAINERID')
    max_ids = _max_batch_container_ids()
    if len(container_ids) > max_ids:
        raise UserInputError(f'container_ids 數量不可超過 {max_ids} 筆')
    normalized_page = _sanitize_page(page)
    normalized_per_page = _sanitize_per_page(per_page)
    spool_query_id = _build_query_tool_batch_query_id("history", container_ids)
    spool_namespace = _query_tool_batch_namespace("history")

    try:
        spool_workcenters = None
        if workcenter_groups:
            spool_workcenters = _get_workcenters_for_groups(workcenter_groups) or None
        spool_result, spool_meta = _try_query_tool_spool_page(
            namespace=spool_namespace,
            query_id=spool_query_id,
            page=normalized_page,
            per_page=normalized_per_page,
            workcenter_names=spool_workcenters,
        )
        if spool_result is not None:
            paged_rows = list(spool_result.get("data", []))
            _enrich_workcenter_group(paged_rows)
            return {
                'data': paged_rows,
                'total': int(spool_result.get("total", len(paged_rows)) or 0),
                'container_ids': container_ids,
                'filtered_by_groups': workcenter_groups or [],
                'pagination': spool_result.get("pagination", {
                    "page": 1,
                    "per_page": len(paged_rows),
                    "total": len(paged_rows),
                    "total_pages": 1,
                }),
                'quality_meta': {
                    'status': 'complete',
                    'runtime': 'duckdb',
                    'runtime_path': 'spool',
                    **spool_meta,
                },
            }

        _check_rss_guard("LOT 批次生產履歷查詢")
        events_by_cid, quality_meta = _fetch_domain_records(container_ids, "history")

        rows = []
        for cid in container_ids:
            rows.extend(events_by_cid.get(cid, []))

        # Aggregate partial trackouts (QT-05/QT-06 strict guard)
        if rows:
            _agg_df = aggregate_partial_trackouts(
                pd.DataFrame(rows),
                _PARTIAL_KEY_COLS_4,
                _PARTIAL_NONKEY_COLS_LOT,
                query_id=spool_query_id,
            )
            rows = _agg_df.to_dict(orient='records')

        _store_query_tool_batch_spool(
            namespace=spool_namespace,
            query_id=spool_query_id,
            rows=rows,
        )

        if workcenter_groups:
            workcenters = _get_workcenters_for_groups(workcenter_groups)
            if workcenters:
                workcenter_set = set(workcenters)
                rows = [
                    row for row in rows
                    if row.get('WORKCENTERNAME') in workcenter_set
                ]

        paged_rows, pagination = _paginate_rows(
            rows,
            normalized_page,
            normalized_per_page,
        )

        _enrich_workcenter_group(paged_rows)
        data = _df_to_records(pd.DataFrame(paged_rows))

        logger.debug(
            f"LOT history batch: {len(data)} records for "
            f"{len(container_ids)} containers"
        )

        return {
            'data': data,
            'total': len(rows),
            'container_ids': container_ids,
            'filtered_by_groups': workcenter_groups or [],
            'pagination': pagination,
            'quality_meta': quality_meta,
        }

    except MemoryError:
        raise
    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT history batch query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_lot_associations_batch(
    container_ids: List[str],
    assoc_type: str,
    *,
    page: int = 1,
    per_page: int = 0,
) -> Dict[str, Any]:
    """Get association data for multiple LOTs in a single EventFetcher call.

    Args:
        container_ids: List of CONTAINERIDs (16-char hex)
        assoc_type: One of 'materials', 'rejects', 'holds'

    Returns:
        Dict with 'data' (merged records) and 'total'.
    """
    if not container_ids:
        raise UserInputError('請指定 CONTAINERID')
    max_ids = _max_batch_container_ids()
    if len(container_ids) > max_ids:
        raise UserInputError(f'container_ids 數量不可超過 {max_ids} 筆')

    valid_batch_types = {'materials', 'rejects', 'holds'}
    if assoc_type not in valid_batch_types:
        raise UserInputError(f'批次查詢不支援類型: {assoc_type}')
    normalized_page = _sanitize_page(page)
    normalized_per_page = _sanitize_per_page(per_page)
    spool_query_id = _build_query_tool_batch_query_id(assoc_type, container_ids)
    spool_namespace = _query_tool_batch_namespace(assoc_type)
    reject_policy = _query_tool_reject_policy() if assoc_type == "rejects" else None

    try:
        spool_result, spool_meta = _try_query_tool_spool_page(
            namespace=spool_namespace,
            query_id=spool_query_id,
            page=normalized_page,
            per_page=normalized_per_page,
            reject_policy=reject_policy,
        )
        if spool_result is not None:
            paged_rows = list(spool_result.get("data", []))
            _enrich_workcenter_group(paged_rows)
            return {
                'data': paged_rows,
                'total': int(spool_result.get("total", len(paged_rows)) or 0),
                'container_ids': container_ids,
                'pagination': spool_result.get("pagination", {
                    "page": 1,
                    "per_page": len(paged_rows),
                    "total": len(paged_rows),
                    "total_pages": 1,
                }),
                'quality_meta': {
                    'status': 'complete',
                    'runtime': 'duckdb',
                    'runtime_path': 'spool',
                    **spool_meta,
                },
            }

        _check_rss_guard(f"LOT 批次{assoc_type}查詢")
        events_by_cid, quality_meta = _fetch_domain_records(container_ids, assoc_type)

        rows = []
        for cid in container_ids:
            rows.extend(events_by_cid.get(cid, []))
        _store_query_tool_batch_spool(
            namespace=spool_namespace,
            query_id=spool_query_id,
            rows=rows,
        )

        if assoc_type == "rejects":
            rows = _apply_query_tool_reject_policy(rows)

        # Keep timeline grouping consistent with history rows.
        # Especially for materials, workcenter names like "焊_DB_料" need to map
        # to the same WORKCENTER_GROUP used by LOT history tracks.
        paged_rows, pagination = _paginate_rows(
            rows,
            normalized_page,
            normalized_per_page,
        )
        _enrich_workcenter_group(paged_rows)
        data = _df_to_records(pd.DataFrame(paged_rows))

        logger.debug(
            f"LOT {assoc_type} batch: {len(data)} records for "
            f"{len(container_ids)} containers"
        )

        return {
            'data': data,
            'total': len(rows),
            'container_ids': container_ids,
            'pagination': pagination,
            'quality_meta': quality_meta,
        }

    except MemoryError:
        raise
    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT {assoc_type} batch query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


# ============================================================
# LOT Association Functions
# ============================================================

def get_lot_materials(container_id: str, *, page: int = 1, per_page: int = 0) -> Dict[str, Any]:
    """Get material consumption records for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)
        page: Page number (1-based)
        per_page: Records per page (0 = no pagination)

    Returns:
        Dict with 'data', 'total', 'pagination', 'quality_meta', or 'error'.
    """
    if not container_id:
        raise UserInputError('請指定 CONTAINERID')

    try:
        events_by_cid, quality_meta = _fetch_domain_records([container_id], "materials")
        rows = list(events_by_cid.get(container_id, []))
        paged_rows, pagination = _paginate_rows(
            rows,
            _sanitize_page(page),
            _sanitize_per_page(per_page),
        )
        _enrich_workcenter_group(paged_rows)
        data = _df_to_records(pd.DataFrame(paged_rows))

        logger.debug(f"LOT materials: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(rows),
            'container_id': container_id,
            'pagination': pagination,
            'quality_meta': quality_meta,
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT materials query failed for {container_id}: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_lot_rejects(container_id: str, *, page: int = 1, per_page: int = 0) -> Dict[str, Any]:
    """Get reject (defect) records for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)
        page: Page number (1-based)
        per_page: Records per page (0 = no pagination)

    Returns:
        Dict with 'data', 'total', 'pagination', 'quality_meta', or 'error'.
    """
    if not container_id:
        raise UserInputError('請指定 CONTAINERID')

    try:
        events_by_cid, quality_meta = _fetch_domain_records([container_id], "rejects")
        rows = list(events_by_cid.get(container_id, []))
        rows = _apply_query_tool_reject_policy(rows)
        paged_rows, pagination = _paginate_rows(
            rows,
            _sanitize_page(page),
            _sanitize_per_page(per_page),
        )
        _enrich_workcenter_group(paged_rows)
        data = _df_to_records(pd.DataFrame(paged_rows))

        logger.debug(f"LOT rejects: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(rows),
            'container_id': container_id,
            'pagination': pagination,
            'quality_meta': quality_meta,
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT rejects query failed for {container_id}: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_lot_holds(container_id: str, *, page: int = 1, per_page: int = 0) -> Dict[str, Any]:
    """Get HOLD/RELEASE records for a LOT.

    Args:
        container_id: CONTAINERID (16-char hex)
        page: Page number (1-based)
        per_page: Records per page (0 = no pagination)

    Returns:
        Dict with 'data', 'total', 'pagination', 'quality_meta', or 'error'.
    """
    if not container_id:
        raise UserInputError('請指定 CONTAINERID')

    try:
        events_by_cid, quality_meta = _fetch_domain_records([container_id], "holds")
        rows = list(events_by_cid.get(container_id, []))
        paged_rows, pagination = _paginate_rows(
            rows,
            _sanitize_page(page),
            _sanitize_per_page(per_page),
        )
        data = _df_to_records(pd.DataFrame(paged_rows))

        logger.debug(f"LOT holds: {len(data)} records for {container_id}")

        return {
            'data': data,
            'total': len(rows),
            'container_id': container_id,
            'pagination': pagination,
            'quality_meta': quality_meta,
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT holds query failed for {container_id}: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_lot_split_merge_history(
    work_order: str,
    current_container_id: str = None,
    full_history: bool = False,
) -> Dict[str, Any]:
    """Get complete split/merge history for a work order (完整拆併批歷史).

    Queries DW_MES_HM_LOTMOVEOUT for SplitLot and CombineLot operations
    throughout the entire production history.

    Uses MFGORDERNAME (indexed) instead of CONTAINERID for much better performance.

    Operation sources (CALLBYCDONAME):
    - AssemblyMotherLotSchePrep: Assembly mother lot scheduling
    - LotSplit: Standard lot split
    - PJ_TMTTCombine: TMTT combine operation

    LOT ID patterns:
    - A00-001-01: Split at production station (製程站點拆分)
    - A00-001-01C: Split at TMTT (TMTT 拆分)

    Args:
        work_order: MFGORDERNAME value (e.g., GA25120713)
        current_container_id: Current LOT's CONTAINERID for highlighting
        full_history: If True, query complete history using slow connection.
            If False (default), query only last 6 months with row limit.

    Returns:
        Dict with 'data' (split/merge history records) and 'total', or 'error'.
    """
    if not work_order:
        raise UserInputError('請指定工單號')

    try:
        builder = QueryBuilder()
        builder.add_in_condition("MFGORDERNAME", [work_order])
        fast_time_window = "AND h.TXNDATE >= ADD_MONTHS(SYSDATE, -6)"
        fast_row_limit = "FETCH FIRST 500 ROWS ONLY"
        sql = SQLLoader.load_with_params(
            "query_tool/lot_split_merge_history",
            WORK_ORDER_FILTER=builder.get_conditions_sql(),
            TIME_WINDOW="" if full_history else fast_time_window,
            ROW_LIMIT="" if full_history else fast_row_limit,
        )
        params = builder.params

        mode = "full" if full_history else "fast"
        logger.info(
            f"Starting split/merge history query for MFGORDERNAME={work_order} mode={mode}"
        )

        # Both modes use slow query path for timeout protection.
        df = read_sql_df_slow(sql, params)
        data = _df_to_records(df)

        # Process records for display
        processed = []
        for record in data:
            op_type = record.get('OPERATION_TYPE', '')

            # Determine operation display name
            if op_type == 'SplitLot':
                op_display = '拆批'
            elif op_type == 'CombineLot':
                op_display = '併批'
            else:
                op_display = op_type

            target_cid = record.get('TARGET_CONTAINERID')
            source_cid = record.get('SOURCE_CONTAINERID')

            processed.append({
                'history_id': record.get('HISTORYMAINLINEID'),
                'operation_type': op_type,
                'operation_type_display': op_display,
                'target_container_id': target_cid,
                'target_lot': record.get('TARGET_LOT'),
                'source_container_id': source_cid,
                'source_lot': record.get('SOURCE_LOT'),
                'target_qty': record.get('TARGET_QTY'),
                'txn_date': record.get('TXNDATE'),
                # Highlight if this record involves the current LOT
                'is_current_lot_source': current_container_id and source_cid == current_container_id,
                'is_current_lot_target': current_container_id and target_cid == current_container_id,
            })

        logger.info(f"Split/merge history completed: {len(processed)} records for MFGORDERNAME={work_order}")

        return {
            'data': processed,
            'total': len(processed),
            'work_order': work_order,
            'mode': mode,
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        error_str = str(exc)
        logger.error(f"Split/merge history query failed for MFGORDERNAME={work_order}: {exc}")

        # Check for timeout error (DPY-4024, ORA-01013, or TimeoutError from read_sql_df_slow)
        if 'timeout' in error_str.lower() or 'DPY-4024' in error_str or 'ORA-01013' in error_str:
            raise QueryTimeoutError('查詢逾時，請縮小查詢範圍', cause=exc)

        raise InternalQueryError('查詢失敗', cause=exc)


def _get_mfg_order_for_lot(container_id: str) -> Optional[str]:
    """Get MFGORDERNAME for a LOT from DW_MES_CONTAINER.

    Note: MFGORDERNAME is the field used in DW_MES_HM_LOTMOVEOUT (indexed).
    This may differ from PJ_WORKORDER in some cases.

    Args:
        container_id: CONTAINERID (16-char hex)

    Returns:
        MFGORDERNAME string (e.g., 'GA25120713') or None if not found.
    """
    try:
        sql = """
        SELECT MFGORDERNAME
        FROM DWH.DW_MES_CONTAINER
        WHERE CONTAINERID = :container_id
          AND MFGORDERNAME IS NOT NULL
        """
        df = read_sql_df_slow(sql, {'container_id': container_id})
        if not df.empty:
            return df.iloc[0]['MFGORDERNAME']
        return None
    except Exception as exc:
        logger.warning(f"Failed to get MFGORDERNAME for {container_id}: {exc}")
        return None


def get_lot_splits(
    container_id: str,
    include_production_history: bool = True,
    full_history: bool = False,
) -> Dict[str, Any]:
    """Get combined split/merge data for a LOT (拆併批紀錄).

    Data sources:
    1. TMTT serial number mapping (DW_MES_PJ_COMBINEDASSYLOTS) - always included, fast
    2. Production split/merge history (DW_MES_HM_LOTMOVEOUT) - uses MFGORDERNAME index

    PERFORMANCE NOTE:
    Production history now queries by MFGORDERNAME (indexed) instead of CONTAINERID
    for much better performance (~1 second vs 40+ seconds).

    Args:
        container_id: CONTAINERID (16-char hex)
        include_production_history: If True (default), include production history query.
        full_history: If True, query split/merge history without fast-mode limits.

    Returns:
        Dict with 'production_history', 'serial_numbers', and totals.
    """
    if not container_id:
        raise UserInputError('請指定 CONTAINERID')

    result = {
        'production_history': [],
        'serial_numbers': [],
        'total_history': 0,
        'total_serial_numbers': 0,
        'container_id': container_id,
        'production_history_skipped': not include_production_history,
    }

    # Add skip reason message if production history is disabled
    if not include_production_history:
        result['production_history_skip_reason'] = (
            '生產拆併批歷史查詢已暫時停用（資料表 DW_MES_HM_LOTMOVEOUT 目前無索引）。'
            '目前僅顯示 TMTT 成品流水號對應資料。'
        )

    # 1. Get production split/merge history by MFGORDERNAME (indexed, fast)
    if include_production_history:
        # Get MFGORDERNAME for this LOT (used in DW_MES_HM_LOTMOVEOUT)
        logger.info(f"[DEBUG] Getting MFGORDERNAME for container_id={container_id}")
        mfg_order = _get_mfg_order_for_lot(container_id)
        logger.info(f"[DEBUG] Got MFGORDERNAME={mfg_order} for container_id={container_id}")

        if mfg_order:
            logger.info(f"Querying production history for MFGORDERNAME={mfg_order} (LOT: {container_id})")
            try:
                history_result = get_lot_split_merge_history(
                    work_order=mfg_order,
                    current_container_id=container_id,
                    full_history=full_history,
                )
                logger.info(f"[DEBUG] history_result keys: {list(history_result.keys())}")
                logger.info(f"[DEBUG] history_result total: {history_result.get('total', 0)}")
                result['production_history'] = history_result.get('data', [])
                result['total_history'] = history_result.get('total', 0)
                result['work_order'] = mfg_order
                logger.info(f"[DEBUG] production_history has {len(result['production_history'])} records")
            except QueryTimeoutError:
                # Timeout error - show user-friendly message
                result['production_history_timeout'] = True
                result['production_history_timeout_message'] = (
                    '生產拆併批歷史查詢超時（超過 120 秒）。此表格（DW_MES_HM_LOTMOVEOUT）'
                    '有 4800 萬筆資料且無索引，查詢時間無法預估。僅顯示 TMTT 成品流水號對應資料。'
                )
                result['work_order'] = mfg_order
                logger.warning(f"Production history query timed out for {mfg_order}")
            except Exception as history_exc:
                # Other error
                result['production_history_error'] = str(history_exc)
                logger.error(f"[DEBUG] history_result error: {history_exc}")
        else:
            logger.warning(f"Could not find MFGORDERNAME for {container_id}, skipping production history")
            result['production_history_skip_reason'] = '無法取得工單號，跳過生產拆併批查詢。'

    # 2. Get TMTT serial number mapping (fast - CONTAINERID has index)
    try:
        sql = SQLLoader.load("query_tool/lot_splits")
        params = {'container_id': container_id}

        df = read_sql_df_slow(sql, params)
        data = _df_to_records(df)

        # Group by FINISHEDNAME to show combined structure
        grouped = {}
        total_good_die = 0

        for record in data:
            sn = record.get('FINISHEDNAME', '')
            if not sn or sn == 'Unknown':
                continue

            if sn not in grouped:
                grouped[sn] = {
                    'serial_number': sn,
                    'lots': [],
                    'total_good_die': 0,
                }

            ratio = record.get('PJ_COMBINEDRATIO')
            good_die = record.get('PJ_GOODDIEQTY')

            grouped[sn]['lots'].append({
                'container_id': record.get('CONTAINERID'),
                'lot_id': record.get('LOT_ID'),
                'work_order': record.get('PJ_WORKORDER'),
                'combine_ratio': ratio,
                'combine_ratio_pct': f"{ratio * 100:.1f}%" if ratio else '-',
                'good_die_qty': good_die,
                'original_good_die_qty': record.get('PJ_ORIGINALGOODDIEQTY'),
                'original_start_date': record.get('ORIGINALSTARTDATE'),
                'is_current': record.get('CONTAINERID') == container_id,
            })

            if good_die:
                grouped[sn]['total_good_die'] += good_die
                total_good_die += good_die

        result['serial_numbers'] = list(grouped.values())
        result['total_serial_numbers'] = len(grouped)
        result['total_good_die'] = total_good_die

        logger.debug(f"LOT splits: {result['total_history']} history + {result['total_serial_numbers']} serial numbers for {container_id}")

    except Exception as exc:
        logger.error(f"LOT splits query failed for {container_id}: {exc}")
        # Don't fail completely if serial number query fails
        result['serial_number_error'] = str(exc)

    return result


def get_lot_jobs(
    equipment_id: str,
    time_start: str,
    time_end: str
) -> Dict[str, Any]:
    """Get JOB records for equipment during LOT processing time.

    Note: EQUIPMENTID = RESOURCEID (same ID system).

    Args:
        equipment_id: Equipment ID (EQUIPMENTID from LOTWIPHISTORY)
        time_start: Start time (ISO format)
        time_end: End time (ISO format)

    Returns:
        Dict with 'data' (job records) and 'total', or 'error'.
    """
    if not all([equipment_id, time_start, time_end]):
        raise UserInputError('請指定設備和時間範圍')

    try:
        # Parse times
        if isinstance(time_start, str):
            start = datetime.strptime(time_start, '%Y-%m-%d %H:%M:%S')
        else:
            start = time_start

        if isinstance(time_end, str):
            end = datetime.strptime(time_end, '%Y-%m-%d %H:%M:%S')
        else:
            end = time_end

        sql = SQLLoader.load("query_tool/lot_jobs")
        params = {
            'equipment_id': equipment_id,
            'time_start': start,
            'time_end': end,
        }

        df = read_sql_df_slow(sql, params)
        data = _df_to_records(df)

        logger.debug(f"LOT jobs: {len(data)} records for {equipment_id}")

        return {
            'data': data,
            'total': len(data),
            'equipment_id': equipment_id,
            'time_range': {'start': time_start, 'end': time_end},
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"LOT jobs query failed for {equipment_id}: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_lot_jobs_with_history(
    equipment_id: str,
    time_start: str,
    time_end: str
) -> Dict[str, Any]:
    """Get JOB records with full transaction history for export.

    Joins DW_MES_JOB with DW_MES_JOBTXNHISTORY so each row contains
    both job-level and transaction-level columns, matching the pattern
    used by the job-query export.

    Args:
        equipment_id: Equipment ID (RESOURCEID)
        time_start: Start time (ISO format)
        time_end: End time (ISO format)

    Returns:
        Dict with 'data' (flattened job+txn records) and 'total', or 'error'.
    """
    if not all([equipment_id, time_start, time_end]):
        raise UserInputError('請指定設備和時間範圍')

    try:
        if isinstance(time_start, str):
            start = datetime.strptime(time_start, '%Y-%m-%d %H:%M:%S')
        else:
            start = time_start

        if isinstance(time_end, str):
            end = datetime.strptime(time_end, '%Y-%m-%d %H:%M:%S')
        else:
            end = time_end

        sql = SQLLoader.load("query_tool/lot_jobs_with_txn")
        params = {
            'equipment_id': equipment_id,
            'time_start': start,
            'time_end': end,
        }

        df = read_sql_df_slow(sql, params)
        data = _df_to_records(df)

        logger.debug(
            f"LOT jobs with txn history: {len(data)} records for {equipment_id}"
        )

        return {
            'data': data,
            'total': len(data),
            'equipment_id': equipment_id,
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(
            f"LOT jobs with txn history query failed for {equipment_id}: {exc}"
        )
        raise InternalQueryError('查詢失敗', cause=exc)


# ============================================================
# Lot → Equipment Lookup
# ============================================================

MAX_LOT_EQUIPMENT_INPUT = 100
MAX_PARENT_TRACE_DEPTH = 10


def _resolve_container_ids_by_names(container_names: List[str]) -> Dict[str, str]:
    """Resolve CONTAINERNAME → CONTAINERID using lot_resolve_id SQL.

    Returns:
        Dict mapping CONTAINERNAME (upper) → CONTAINERID.
    """
    builder = QueryBuilder()
    _add_exact_or_pattern_condition(builder, "CONTAINERNAME", container_names)
    sql = SQLLoader.load_with_params(
        "query_tool/lot_resolve_id",
        CONTAINER_FILTER=builder.get_conditions_sql(),
    )
    df = read_sql_df_slow(sql, builder.params, caller="lot_equip:resolve_ids")
    if df is None or df.empty:
        return {}
    records = _df_to_records(df)
    result = {}
    for row in records:
        name = (row.get('CONTAINERNAME') or '').strip().upper()
        cid = (row.get('CONTAINERID') or '').strip()
        if name and cid:
            result[name] = cid
    return result


def _build_two_filters(
    col_a: str, values_a: List[str],
    col_b: str, values_b: List[str],
) -> Tuple[str, str, Dict[str, Any]]:
    """Build two IN-clause filters on a single QueryBuilder to avoid param name collision.

    Returns:
        (filter_a_sql, filter_b_sql, merged_params)
    """
    builder = QueryBuilder()
    builder.add_in_condition(col_a, values_a)
    filter_a = builder.conditions[0] if builder.conditions else "1=1"
    builder.add_in_condition(col_b, values_b)
    filter_b = builder.conditions[1] if len(builder.conditions) > 1 else "1=1"
    return filter_a, filter_b, builder.params


def _check_names_with_equipment(
    container_names: List[str],
    workcenters: List[str],
) -> set:
    """Check which container names have equipment at given workcenters.

    Returns:
        Set of CONTAINERNAME values that have equipment records.
    """
    if not container_names or not workcenters:
        return set()

    container_filter, workcenter_filter, params = _build_two_filters(
        "c.CONTAINERNAME", container_names,
        "h.WORKCENTERNAME", workcenters,
    )

    sql = SQLLoader.load_with_params(
        "query_tool/lot_equipment_check",
        CONTAINER_FILTER=container_filter,
        WORKCENTER_FILTER=workcenter_filter,
    )

    df = read_sql_df_slow(sql, params, caller="lot_equip:check_names")
    if df is None or df.empty:
        return set()
    records = _df_to_records(df)
    return {(r.get('CONTAINERNAME') or '').strip() for r in records} - {''}


def _lookup_equipment_by_names(
    container_names: List[str],
    workcenters: List[str],
) -> List[Dict[str, Any]]:
    """Query lot_equipment_lookup for given container names + workcenters.

    Returns:
        List of result records (EQUIPMENTID, EQUIPMENTNAME, MIN_TRACKIN, MAX_TRACKOUT).
        Empty list if nothing found.
    """
    if not container_names or not workcenters:
        return []

    container_filter, workcenter_filter, params = _build_two_filters(
        "c.CONTAINERNAME", container_names,
        "h.WORKCENTERNAME", workcenters,
    )

    sql = SQLLoader.load_with_params(
        "query_tool/lot_equipment_lookup",
        CONTAINER_FILTER=container_filter,
        WORKCENTER_FILTER=workcenter_filter,
    )

    df = read_sql_df_slow(sql, params, caller="lot_equip:lookup_names")
    if df is None or df.empty:
        return []
    return _df_to_records(df)


def _trace_parents_for_equipment(
    not_found_names: List[str],
    workcenters: List[str],
) -> Tuple[Dict[str, str], List[str]]:
    """For lots without equipment at workcenter, trace up split chain.

    Args:
        not_found_names: LOT names (CONTAINERNAME) with no equipment.
        workcenters: WORKCENTERNAME list for the selected groups.

    Returns:
        (trace_map, found_parent_names)
        trace_map: {original_lot_name: parent_lot_name_that_was_found}
        found_parent_names: parent names that DO have equipment at workcenter.
    """
    from mes_dashboard.services.lineage_engine import LineageEngine

    trace_map: Dict[str, str] = {}
    found_parent_names: List[str] = []

    # Resolve not-found names to CIDs
    name_to_cid = _resolve_container_ids_by_names(not_found_names)
    if not name_to_cid:
        return trace_map, found_parent_names

    cid_to_name: Dict[str, str] = {v: k for k, v in name_to_cid.items()}

    # pending: original_input_name → current_cid being traced
    pending: Dict[str, str] = {}
    for name in not_found_names:
        cid = name_to_cid.get(name.strip().upper())
        if cid:
            pending[name] = cid

    for _depth in range(MAX_PARENT_TRACE_DEPTH):
        if not pending:
            break

        current_cids = list(set(pending.values()))
        split_result = LineageEngine.resolve_split_ancestors(current_cids)
        child_to_parent = split_result.get("child_to_parent", {})
        discovered_names = split_result.get("cid_to_name", {})
        cid_to_name.update(discovered_names)

        if not child_to_parent:
            break

        # Advance each pending entry to its parent
        next_pending: Dict[str, str] = {}
        parent_cids_this_round: set = set()
        for original_name, current_cid in list(pending.items()):
            parent_cid = child_to_parent.get(current_cid)
            if not parent_cid or parent_cid == current_cid:
                # No parent — stop tracing this one
                continue
            parent_cids_this_round.add(parent_cid)
            next_pending[original_name] = parent_cid

        if not parent_cids_this_round:
            break

        # Get parent names (cid_to_name was updated by split_ancestors)
        parent_names_set = {
            cid_to_name[p] for p in parent_cids_this_round if p in cid_to_name
        }

        if not parent_names_set:
            break

        # Check which parent names have equipment at the workcenter
        parents_with_equipment = _check_names_with_equipment(
            list(parent_names_set), workcenters,
        )

        # Partition: found parents vs keep tracing
        still_pending: Dict[str, str] = {}
        for original_name, parent_cid in next_pending.items():
            parent_name = cid_to_name.get(parent_cid, '')
            if parent_name in parents_with_equipment:
                trace_map[original_name] = parent_name
                found_parent_names.append(parent_name)
            elif parent_name:
                # Parent not found either — record and keep tracing
                trace_map[original_name] = parent_name
                still_pending[original_name] = parent_cid

        pending = still_pending

    # Clean trace_map: only keep entries whose final value was found
    found_set = set(found_parent_names)
    trace_map = {k: v for k, v in trace_map.items() if v in found_set}

    return trace_map, list(set(found_parent_names))


def resolve_lot_equipment(
    input_type: str,
    values: List[str],
    workcenter_groups: List[str],
) -> Dict[str, Any]:
    """Look up which equipment processed given lots at workcenter groups.

    For lot_id input: if a lot has no equipment at the workcenter groups,
    traces up the split chain to find a parent lot that does.

    For work_order input: resolves work order to lot IDs first.

    Args:
        input_type: 'lot_id' or 'work_order'
        values: List of LOT IDs or work order numbers.
        workcenter_groups: List of WORKCENTER_GROUP names.

    Returns:
        Dict with equipment_ids, equipment_names, date_range, trace_map.
    """
    if not values:
        raise UserInputError('請輸入至少一筆查詢條件')

    if len(values) > MAX_LOT_EQUIPMENT_INPUT:
        raise UserInputError(f'輸入數量不得超過 {MAX_LOT_EQUIPMENT_INPUT} 筆')

    if input_type not in ('lot_id', 'work_order'):
        raise UserInputError(f'不支援的輸入類型: {input_type}')

    if not workcenter_groups:
        raise UserInputError('請選擇站點群組')

    workcenters = _get_workcenters_for_groups(workcenter_groups)
    if not workcenters:
        group_names = '、'.join(workcenter_groups)
        raise ResourceNotFoundError(f'找不到站點群組「{group_names}」對應的站點')

    try:
        _check_rss_guard("批次追蹤生產設備 lookup")

        # Step 1: Resolve input to container names
        if input_type == 'work_order':
            resolve_result = resolve_lots('work_order', values)
            # resolve_lots now raises on error; this check is a safety belt for any
            # residual dict-based callers that may still exist.
            if 'error' in resolve_result:
                raise UserInputError(resolve_result['error'])
            resolved_data = resolve_result.get('data', [])
            if not resolved_data:
                return {
                    'equipment_ids': [],
                    'equipment_names': [],
                    'date_range': None,
                    'trace_map': {},
                    'not_found_hint': '找不到此工單對應的批次',
                }
            all_names = list({
                row.get('lot_id', '').strip()
                for row in resolved_data
                if row.get('lot_id')
            })
        else:
            # lot_id: use as-is
            all_names = [v.strip() for v in values if v.strip()]

        if not all_names:
            return {
                'equipment_ids': [],
                'equipment_names': [],
                'date_range': None,
                'trace_map': {},
                'not_found_hint': '找不到任何符合的批次',
            }

        # Step 2: Check which input names have equipment at the workcenter
        found_names = _check_names_with_equipment(all_names, workcenters)
        logger.info(
            "Lot equipment check: %s input, %s found at workcenter groups %s",
            len(all_names), len(found_names), workcenter_groups,
        )

        trace_map = {}
        final_names = list(found_names)

        # Step 3: For lot_id, trace not-found names up the split chain
        if input_type == 'lot_id':
            not_found_names = [n for n in all_names if n not in found_names]
            if not_found_names:
                logger.info(
                    "Lot equipment: %s lots not found, tracing parents: %s",
                    len(not_found_names), not_found_names,
                )
                trace_map, found_parent_names = _trace_parents_for_equipment(
                    not_found_names, workcenters,
                )
                final_names.extend(found_parent_names)

        # Step 4: Get equipment details for all matched names
        records = _lookup_equipment_by_names(final_names, workcenters)

        if not records:
            return {
                'equipment_ids': [],
                'equipment_names': [],
                'date_range': None,
                'trace_map': trace_map,
                'not_found_hint': '在指定站點群組中找不到這些批次的設備紀錄',
            }

        equipment_ids = list({r['EQUIPMENTID'] for r in records if r.get('EQUIPMENTID')})
        equipment_names = list({r['EQUIPMENTNAME'] for r in records if r.get('EQUIPMENTNAME')})

        min_trackin = records[0].get('MIN_TRACKIN') if records else None
        max_trackout = records[0].get('MAX_TRACKOUT') if records else None

        date_range = None
        if min_trackin and max_trackout:
            start_dt = str(min_trackin)[:10]
            end_dt = str(max_trackout)[:10]
            date_range = {'start': start_dt, 'end': end_dt}

        logger.info(
            "Lot equipment lookup: input_type=%s, input=%s, equipment=%s, "
            "traced=%s, groups=%s",
            input_type, len(values), len(equipment_ids),
            len(trace_map), workcenter_groups,
        )

        return {
            'equipment_ids': equipment_ids,
            'equipment_names': equipment_names,
            'date_range': date_range,
            'trace_map': trace_map,
            'lot_names': final_names,
        }

    except MemoryError:
        raise
    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"Lot equipment lookup failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


# ============================================================
# Equipment Period Query Functions
# ============================================================

def get_equipment_status_hours(
    equipment_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get status hours statistics for equipment in a time period.

    Calculates OU% = PRD / (PRD + SBY + UDT) × 100%

    Args:
        equipment_ids: List of equipment IDs
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (status hours per equipment) and aggregated totals.
    """
    # Validate inputs
    validation_error = validate_equipment_input(equipment_ids)
    if validation_error:
        raise UserInputError(validation_error)

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        raise UserInputError(validation_error)

    try:
        from mes_dashboard.services.batch_query_engine import compute_query_hash
        from mes_dashboard.core.query_spool_store import load_spooled_df, store_spooled_df

        _QT_EQUIP_SPOOL_NS = "query_tool_equipment"
        _QT_EQUIP_SPOOL_TTL = 300

        cache_hash = compute_query_hash({
            "fn": "equipment_status_hours",
            "equipment_ids": sorted(equipment_ids),
            "start_date": start_date,
            "end_date": end_date,
        })
        spool_query_id = f"qt.equip.{cache_hash}"
        cached_df = load_spooled_df(_QT_EQUIP_SPOOL_NS, spool_query_id)

        if cached_df is not None:
            df = cached_df
        else:
            builder = QueryBuilder()
            builder.add_in_condition("r.RESOURCEID", equipment_ids)
            sql = SQLLoader.load_with_params(
                "query_tool/equipment_status_hours",
                EQUIPMENT_FILTER=builder.get_conditions_sql(),
            )
            params = {'start_date': start_date, 'end_date': end_date}
            params.update(builder.params)
            df = read_sql_df_slow(sql, params)
            if df is not None and not df.empty:
                store_spooled_df(_QT_EQUIP_SPOOL_NS, spool_query_id, df, ttl_seconds=_QT_EQUIP_SPOOL_TTL)

        data = _df_to_records(df)

        # Calculate totals
        total_prd = sum(r.get('PRD_HOURS', 0) or 0 for r in data)
        total_sby = sum(r.get('SBY_HOURS', 0) or 0 for r in data)
        total_udt = sum(r.get('UDT_HOURS', 0) or 0 for r in data)
        total_sdt = sum(r.get('SDT_HOURS', 0) or 0 for r in data)
        total_egt = sum(r.get('EGT_HOURS', 0) or 0 for r in data)
        total_nst = sum(r.get('NST_HOURS', 0) or 0 for r in data)
        total_hours = sum(r.get('TOTAL_HOURS', 0) or 0 for r in data)

        denominator = total_prd + total_sby + total_udt
        total_ou = round(total_prd * 100.0 / denominator, 2) if denominator > 0 else 0

        logger.info(f"Equipment status hours: {len(data)} equipment records")

        return {
            'data': data,
            'total': len(data),
            'totals': {
                'PRD_HOURS': total_prd,
                'SBY_HOURS': total_sby,
                'UDT_HOURS': total_udt,
                'SDT_HOURS': total_sdt,
                'EGT_HOURS': total_egt,
                'NST_HOURS': total_nst,
                'TOTAL_HOURS': total_hours,
                'OU_PERCENT': total_ou,
            },
            'date_range': {'start': start_date, 'end': end_date},
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"Equipment status hours query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_equipment_lots(
    equipment_ids: List[str],
    start_date: str,
    end_date: str,
    *,
    page: int = 1,
    per_page: int = 0,
) -> Dict[str, Any]:
    """Get lots processed by equipment in a time period.

    Args:
        equipment_ids: List of equipment IDs
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (lot records) and 'total'.
    """
    # Validate inputs
    validation_error = validate_equipment_input(equipment_ids)
    if validation_error:
        raise UserInputError(validation_error)

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        raise UserInputError(validation_error)

    try:
        _check_rss_guard("設備批次 LOT 查詢")
        builder = QueryBuilder()
        builder.add_in_condition("h.EQUIPMENTID", equipment_ids)
        sql = SQLLoader.load_with_params(
            "query_tool/equipment_lots",
            EQUIPMENT_FILTER=builder.get_conditions_sql(),
        )

        params = {'start_date': start_date, 'end_date': end_date}
        params.update(builder.params)
        df = read_sql_df_slow(sql, params)
        # Aggregate partial trackouts (QT-05/QT-06 strict guard)
        df = aggregate_partial_trackouts(
            df,
            _PARTIAL_KEY_COLS_4,
            _PARTIAL_NONKEY_COLS_LOT,
            query_id=f"equipment_lots:{start_date}:{end_date}",
        )
        records = _df_to_records(df)
        paged_rows, pagination = _paginate_rows(
            records,
            _sanitize_page(page),
            _sanitize_per_page(per_page),
        )

        logger.info(f"Equipment lots: {len(records)} records")

        return {
            'data': paged_rows,
            'total': len(records),
            'date_range': {'start': start_date, 'end': end_date},
            'pagination': pagination,
        }

    except MemoryError:
        raise
    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"Equipment lots query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_equipment_materials(
    equipment_names: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get material consumption summary for equipment in a time period.

    Note: LOTMATERIALSHISTORY uses EQUIPMENTNAME for filtering.

    Args:
        equipment_names: List of equipment names
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (material summary) and 'total'.
    """
    if not equipment_names:
        raise UserInputError('請選擇至少一台設備')

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        raise UserInputError(validation_error)

    try:
        _check_rss_guard("設備原料消耗查詢")
        builder = QueryBuilder()
        builder.add_in_condition("EQUIPMENTNAME", equipment_names)
        sql = SQLLoader.load_with_params(
            "query_tool/equipment_materials",
            EQUIPMENT_FILTER=builder.get_conditions_sql(),
        )

        params = {'start_date': start_date, 'end_date': end_date}
        params.update(builder.params)
        df = read_sql_df_slow(sql, params)
        data = _df_to_records(df)

        logger.info(f"Equipment materials: {len(data)} records")

        return {
            'data': data,
            'total': len(data),
            'date_range': {'start': start_date, 'end': end_date},
        }

    except MemoryError:
        raise
    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"Equipment materials query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_equipment_rejects(
    equipment_ids: List[str],
    start_date: str,
    end_date: str,
    workcenter_groups: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get per-reject-event detail rows for lots that passed through equipment.

    Resolves equipment IDs via LOTWIPHISTORY (TRACKINTIMESTAMP within window) to
    a DISTINCT CONTAINERID set, then returns LOTREJECTHISTORY rows for those
    containers. The reject event EQUIPMENTNAME may differ from the queried
    equipment (cross-station case — intentional per QT-07).

    Args:
        equipment_ids: List of equipment IDs (EQUIPMENTID from LOTWIPHISTORY)
        start_date: Start date (YYYY-MM-DD) — applied on TRACKINTIMESTAMP
        end_date: End date (YYYY-MM-DD)
        workcenter_groups: Optional list of WORK_CENTER_GROUP names to filter
            reject events by station group. When None, all rejects are returned.

    Returns:
        Dict with 'data' (per-reject-event detail rows) and 'total'.
    """
    validation_error = validate_equipment_input(equipment_ids)
    if validation_error:
        raise UserInputError(validation_error)

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        raise UserInputError(validation_error)

    try:
        _check_rss_guard("設備批次不良品查詢")
        builder = QueryBuilder()
        builder.add_in_condition("h.EQUIPMENTID", equipment_ids)

        if workcenter_groups:
            wg_builder = QueryBuilder()
            wg_builder._param_counter = builder._param_counter
            wg_builder.add_in_condition("WORKCENTER_GROUP", workcenter_groups)
            builder._param_counter = wg_builder._param_counter
            builder.params.update(wg_builder.params)
            workcenter_filter = wg_builder.get_conditions_sql()
        else:
            workcenter_filter = '1=1'

        sql = SQLLoader.load_with_params(
            "query_tool/equipment_lot_rejects",
            EQUIPMENT_FILTER=builder.get_conditions_sql(),
            WORKCENTER_FILTER=workcenter_filter,
        )

        params = {'start_date': start_date, 'end_date': end_date}
        params.update(builder.params)
        df = read_sql_df_slow(sql, params)
        data = _df_to_records(df)

        logger.info(f"Equipment lot rejects: {len(data)} records")

        return {
            'data': data,
            'total': len(data),
            'date_range': {'start': start_date, 'end': end_date},
        }

    except MemoryError:
        raise
    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"Equipment lot rejects query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


def get_equipment_jobs(
    equipment_ids: List[str],
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """Get JOB records for equipment in a time period.

    Note: DW_MES_JOB uses RESOURCEID (= EQUIPMENTID).

    Args:
        equipment_ids: List of equipment IDs (RESOURCEID)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        Dict with 'data' (job records) and 'total'.
    """
    # Validate inputs
    validation_error = validate_equipment_input(equipment_ids)
    if validation_error:
        raise UserInputError(validation_error)

    validation_error = validate_date_range(start_date, end_date)
    if validation_error:
        raise UserInputError(validation_error)

    try:
        builder = QueryBuilder()
        builder.add_in_condition("RESOURCEID", equipment_ids)
        sql = SQLLoader.load_with_params(
            "query_tool/equipment_jobs",
            EQUIPMENT_FILTER=builder.get_conditions_sql(),
        )

        params = {'start_date': start_date, 'end_date': end_date}
        params.update(builder.params)
        df = read_sql_df_slow(sql, params)
        data = _df_to_records(df)

        logger.info(f"Equipment jobs: {len(data)} records")

        return {
            'data': data,
            'total': len(data),
            'date_range': {'start': start_date, 'end': end_date},
        }

    except (UserInputError, ResourceNotFoundError, QueryTimeoutError, DataContractError, InternalQueryError):
        raise
    except Exception as exc:
        logger.error(f"Equipment jobs query failed: {exc}")
        raise InternalQueryError('查詢失敗', cause=exc)


# ============================================================
# Export Functions
# ============================================================

def export_to_csv(
    data: List[Dict[str, Any]],
    columns: Optional[List[str]] = None
) -> str:
    """Export data to CSV string.

    Args:
        data: List of records to export
        columns: Optional column order. If None, uses keys from first record.

    Returns:
        CSV string with UTF-8 BOM for Excel compatibility.
    """
    if not data:
        return ''

    output = io.StringIO()
    output.write('\ufeff')  # UTF-8 BOM for Excel

    # Determine columns
    if columns is None:
        columns = list(data[0].keys())

    writer = csv.writer(output)
    writer.writerow(columns)

    for record in data:
        row = []
        for col in columns:
            value = record.get(col)
            if value is None:
                row.append('')
            else:
                row.append(str(value))
        writer.writerow(row)

    return output.getvalue()


def generate_csv_stream(
    data: List[Dict[str, Any]],
    columns: Optional[List[str]] = None
) -> Generator[str, None, None]:
    """Generate CSV content as a stream.

    Args:
        data: List of records to export
        columns: Optional column order

    Yields:
        CSV rows as strings
    """
    if not data:
        return

    # Determine columns
    if columns is None:
        columns = list(data[0].keys())

    output = io.StringIO()
    writer = csv.writer(output)

    # Write BOM and header
    output.write('\ufeff')
    writer.writerow(columns)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)

    # Write data rows
    for record in data:
        row = []
        for col in columns:
            value = record.get(col)
            if value is None:
                row.append('')
            else:
                row.append(str(value))
        writer.writerow(row)
        yield output.getvalue()
        output.truncate(0)
        output.seek(0)


# ============================================================
# Equipment Recent Jobs (for suspect context panel)
# ============================================================

def get_equipment_recent_jobs(equipment_id: str) -> Dict[str, Any]:
    """Get recent JOB records for a specific equipment (last 30 days, top 5).

    Used by the suspect machine context panel in mid-section-defect analysis.

    Returns:
        Dict with 'data' list and 'total' count.
    """
    equipment_id = str(equipment_id or '').strip()
    if not equipment_id:
        raise ValueError('請指定設備ID')

    sql = SQLLoader.load("query_tool/equipment_recent_jobs")
    df = read_sql_df(sql, {'equipment_id': equipment_id})

    if df is None or df.empty:
        return {'data': [], 'total': 0}

    data = []
    for _, row in df.iterrows():
        data.append({
            'JOBID': str(row.get('JOBID') or ''),
            'JOBSTATUS': str(row.get('JOBSTATUS') or ''),
            'JOBMODELNAME': str(row.get('JOBMODELNAME') or ''),
            'CREATEDATE': str(row.get('CREATEDATE') or ''),
            'COMPLETEDATE': str(row.get('COMPLETEDATE') or ''),
            'CAUSECODENAME': str(row.get('CAUSECODENAME') or ''),
            'REPAIRCODENAME': str(row.get('REPAIRCODENAME') or ''),
            'RESOURCENAME': str(row.get('RESOURCENAME') or ''),
        })

    return {'data': data, 'total': len(data)}
