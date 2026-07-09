# -*- coding: utf-8 -*-
"""Parquet spool store for large query results.

Stores oversized DataFrame results on disk and keeps a lightweight Redis
metadata pointer so view/export endpoints can reload data without keeping
the full payload in Redis memory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from decimal import Decimal
from numbers import Real
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from mes_dashboard.core.exceptions import LockUnavailableError
from mes_dashboard.core.redis_client import (
    get_control_redis_client,
    get_key,
    get_redis_client,
    release_lock,
    try_acquire_lock,
)

logger = logging.getLogger("mes_dashboard.query_spool_store")


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


# Canonical env var names.  Legacy REJECT_ENGINE_* names are accepted as
# fallbacks so existing deployments continue to work without reconfiguration.
QUERY_SPOOL_ENABLED = _bool_env("QUERY_SPOOL_ENABLED", _bool_env("REJECT_ENGINE_SPILL_ENABLED", True))
QUERY_SPOOL_DIR = Path(os.getenv("QUERY_SPOOL_DIR", "tmp/query_spool"))
QUERY_SPOOL_TTL_SECONDS = max(
    _int_env("SPOOL_TTL_SECONDS", _int_env("REJECT_ENGINE_SPOOL_TTL_SECONDS", 10800)), 300
)
QUERY_SPOOL_MAX_BYTES = max(
    _int_env("QUERY_SPOOL_MAX_BYTES", _int_env("REJECT_ENGINE_SPOOL_MAX_BYTES", 10_737_418_240)), 1
)
QUERY_SPOOL_WARN_RATIO = min(
    max(_float_env("QUERY_SPOOL_WARN_RATIO", _float_env("REJECT_ENGINE_SPOOL_WARN_RATIO", 0.85)), 0.1), 1.0
)
QUERY_SPOOL_CLEANUP_INTERVAL_SECONDS = max(
    _int_env(
        "QUERY_SPOOL_CLEANUP_INTERVAL_SECONDS",
        _int_env("REJECT_ENGINE_SPOOL_CLEANUP_INTERVAL_SECONDS", 300),
    ),
    30,
)
QUERY_SPOOL_ORPHAN_GRACE_SECONDS = max(
    _int_env(
        "QUERY_SPOOL_ORPHAN_GRACE_SECONDS",
        _int_env("REJECT_ENGINE_SPOOL_ORPHAN_GRACE_SECONDS", 600),
    ),
    60,
)
_SPOOL_SCHEMA_VERSION = 1
_VALID_ID_RE = re.compile(r"^[A-Za-z0-9._-]{4,128}$")

_WORKER_THREAD: threading.Thread | None = None
_STOP_EVENT = threading.Event()
_CLEANUP_LOCK_NAME = "query_spool_cleanup"


def _safe_query_id(query_id: str) -> Optional[str]:
    value = str(query_id or "").strip()
    if not value or not _VALID_ID_RE.match(value):
        return None
    return value


def _normalize_namespace(namespace: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]", "_", str(namespace or "default").strip())
    return value or "default"


def _spool_root() -> Path:
    return QUERY_SPOOL_DIR.resolve()


def _meta_key(namespace: str, query_id: str) -> str:
    ns = _normalize_namespace(namespace)
    return f"{ns}:spool_meta:{query_id}"


def _target_path(namespace: str, query_id: str) -> Path:
    root = _spool_root()
    ns = _normalize_namespace(namespace)
    path = (root / ns / f"{query_id}.parquet").resolve()
    root_str = str(root)
    if not str(path).startswith(f"{root_str}{os.sep}"):
        raise ValueError("Invalid spool target path")
    return path


def _move_into_place(src_path: Path, dest_path: Path) -> None:
    """Move a temp parquet into place, tolerating Docker cross-device mounts."""
    src = Path(src_path)
    dest = Path(dest_path)
    try:
        src.replace(dest)
    except OSError:
        shutil.move(str(src), str(dest))


def _safe_stage(stage: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(stage or "").strip()) or "default"


def _stage_meta_key(namespace: str, query_id: str, stage: str) -> str:
    ns = _normalize_namespace(namespace)
    return f"{ns}:spool_stage:{query_id}:{_safe_stage(stage)}"


def _stage_index_key(namespace: str, query_id: str) -> str:
    ns = _normalize_namespace(namespace)
    return f"{ns}:spool_stages:{query_id}"


def _stage_target_path(namespace: str, query_id: str, stage: str) -> Path:
    root = _spool_root()
    ns = _normalize_namespace(namespace)
    path = (root / ns / f"{query_id}_{_safe_stage(stage)}.parquet").resolve()
    root_str = str(root)
    if not str(path).startswith(f"{root_str}{os.sep}"):
        raise ValueError("Invalid spool stage target path")
    return path


def _path_from_relative(relative_path: str) -> Optional[Path]:
    try:
        root = _spool_root()
        rel = Path(str(relative_path)).as_posix().lstrip("/")
        path = (root / rel).resolve()
        root_str = str(root)
        if not str(path).startswith(f"{root_str}{os.sep}"):
            return None
        return path
    except Exception:
        return None


def _normalize_decimal_object_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    normalized = df.copy()
    for col in normalized.columns:
        series = normalized[col]
        if series.dtype != "object":
            continue

        non_null = series.dropna()
        if non_null.empty:
            continue

        has_decimal = non_null.map(lambda value: isinstance(value, Decimal)).any()
        if not has_decimal:
            continue

        is_numeric_like = non_null.map(
            lambda value: isinstance(value, (Decimal, Real)) and not isinstance(value, bool)
        ).all()
        if is_numeric_like:
            normalized[col] = pd.to_numeric(series, errors="coerce")
        else:
            normalized[col] = series.map(
                lambda value: str(value) if isinstance(value, Decimal) else value
            )
    return normalized


def _estimate_spool_size_bytes(df: pd.DataFrame) -> int:
    mem_bytes = int(df.memory_usage(deep=True).sum())
    # Typical parquet compression ratio is ~2-5x; use conservative 45% estimate.
    return max(int(mem_bytes * 0.45), 1_048_576)


def _get_spool_size_bytes() -> int:
    root = _spool_root()
    if not root.exists():
        return 0
    total = 0
    for file_path in root.rglob("*.parquet"):
        try:
            total += int(file_path.stat().st_size)
        except OSError:
            continue
    return total


def _columns_hash(columns: list[str]) -> str:
    joined = "|".join(columns)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _ensure_capacity(required_bytes: int) -> bool:
    used = _get_spool_size_bytes()
    projected = used + max(required_bytes, 0)
    usage_ratio = projected / max(QUERY_SPOOL_MAX_BYTES, 1)
    if usage_ratio >= QUERY_SPOOL_WARN_RATIO:
        logger.warning(
            "Query spool usage high: %.1f%% (%d/%d bytes)",
            usage_ratio * 100,
            projected,
            QUERY_SPOOL_MAX_BYTES,
        )
    if projected <= QUERY_SPOOL_MAX_BYTES:
        return True

    cleanup_expired_spool(namespace=None)
    used_after_cleanup = _get_spool_size_bytes()
    if used_after_cleanup + max(required_bytes, 0) <= QUERY_SPOOL_MAX_BYTES:
        return True

    logger.warning(
        "Query spool over capacity after cleanup: required=%d used=%d cap=%d",
        required_bytes,
        used_after_cleanup,
        QUERY_SPOOL_MAX_BYTES,
    )
    return False


def get_spool_metadata(namespace: str, query_id: str) -> Optional[dict[str, Any]]:
    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        return None
    client = get_redis_client()
    if client is None:
        return None
    key = get_key(_meta_key(namespace, safe_query_id))
    try:
        raw = client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            client.delete(key)
            return None
        return payload
    except Exception as exc:
        logger.warning("Failed to read spool metadata for %s: %s", safe_query_id, exc)
        return None


def store_spooled_df(
    namespace: str,
    query_id: str,
    df: pd.DataFrame,
    *,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """Persist DataFrame to parquet and save metadata pointer in Redis."""
    if not QUERY_SPOOL_ENABLED or df is None or df.empty:
        return False

    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        logger.warning("Invalid query_id for spool store: %s", query_id)
        return False

    ttl = max(int(ttl_seconds or QUERY_SPOOL_TTL_SECONDS), 60)
    estimated_bytes = _estimate_spool_size_bytes(df)
    if not _ensure_capacity(estimated_bytes):
        return False

    client = get_redis_client()
    if client is None:
        logger.warning("Redis unavailable, skip spool store for query_id=%s", safe_query_id)
        return False

    try:
        path = _target_path(namespace, safe_query_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        normalized = _normalize_decimal_object_columns(df)
        normalized.to_parquet(tmp_path, engine="pyarrow", index=False)
        tmp_path.replace(path)

        now_ts = int(time.time())
        columns = [str(col) for col in normalized.columns]
        metadata = {
            "schema_version": _SPOOL_SCHEMA_VERSION,
            "namespace": _normalize_namespace(namespace),
            "query_id": safe_query_id,
            "relative_path": str(path.relative_to(_spool_root())),
            "row_count": int(len(normalized)),
            "column_count": int(len(columns)),
            "columns_hash": _columns_hash(columns),
            "created_at": now_ts,
            "expires_at": now_ts + ttl,
            "file_size_bytes": int(path.stat().st_size),
        }
        client.setex(
            get_key(_meta_key(namespace, safe_query_id)),
            ttl,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        )
        return True
    except Exception as exc:
        logger.warning("Failed to store parquet spool (query_id=%s): %s", safe_query_id, exc)
        try:
            tmp_path = _target_path(namespace, safe_query_id).with_suffix(".tmp")
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False


def load_spooled_df(namespace: str, query_id: str) -> Optional[pd.DataFrame]:
    """Load DataFrame from spool metadata pointer."""
    if not QUERY_SPOOL_ENABLED:
        return None

    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        return None

    metadata = get_spool_metadata(namespace, safe_query_id)
    if metadata is None:
        return None

    expires_at = int(metadata.get("expires_at") or 0)
    if expires_at and expires_at <= int(time.time()):
        clear_spooled_df(namespace, safe_query_id)
        return None

    path = _path_from_relative(str(metadata.get("relative_path") or ""))
    if path is None or not path.exists():
        clear_spooled_df(namespace, safe_query_id, remove_file=False)
        return None

    try:
        df = pd.read_parquet(path, engine="pyarrow")
    except Exception as exc:
        logger.warning("Failed to read spool parquet (%s): %s", path, exc)
        clear_spooled_df(namespace, safe_query_id)
        return None

    expected_hash = str(metadata.get("columns_hash") or "")
    if expected_hash:
        current_hash = _columns_hash([str(col) for col in df.columns])
        if current_hash != expected_hash:
            logger.warning(
                "Spool metadata mismatch for query_id=%s (columns hash mismatch)",
                safe_query_id,
            )
            clear_spooled_df(namespace, safe_query_id)
            return None

    return df


def read_spool_records(namespace: str, query_id: str) -> Optional[list[dict[str, Any]]]:
    """Read spool parquet via DuckDB and return list-of-dict records.

    Handles datetime formatting (YYYY-MM-DD HH:MM:SS) and null→None
    conversion, matching the behaviour of the former pandas iterrows path.
    Returns None when spool is missing or expired.
    """
    spool_path = get_spool_file_path(namespace, query_id)
    if spool_path is None:
        return None

    conn = None
    try:
        from mes_dashboard.core.duckdb_runtime import create_heavy_query_connection

        conn = create_heavy_query_connection()
        rel = conn.read_parquet(spool_path)
        columns = rel.columns
        types = rel.types
        rows = rel.fetchall()

        # Identify timestamp columns for formatting
        ts_indices = {
            i for i, t in enumerate(types) if "TIMESTAMP" in str(t).upper()
        }

        records: list[dict[str, Any]] = []
        for row in rows:
            record: dict[str, Any] = {}
            for i, col in enumerate(columns):
                val = row[i]
                if val is None:
                    record[col] = None
                elif i in ts_indices:
                    record[col] = val.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    record[col] = val
            records.append(record)
        return records
    except Exception as exc:
        logger.warning("read_spool_records failed (ns=%s, id=%s): %s", namespace, query_id, exc)
        return None
    finally:
        # Close in finally so a read_parquet/fetchall failure cannot leak the
        # DuckDB connection (it previously closed only on the success path).
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_spool_file_path(namespace: str, query_id: str) -> Optional[str]:
    """Resolve spool parquet path for query_id without loading DataFrame."""
    if not QUERY_SPOOL_ENABLED:
        return None

    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        return None

    metadata = get_spool_metadata(namespace, safe_query_id)
    if metadata is None:
        return None

    expires_at = int(metadata.get("expires_at") or 0)
    if expires_at and expires_at <= int(time.time()):
        clear_spooled_df(namespace, safe_query_id)
        return None

    path = _path_from_relative(str(metadata.get("relative_path") or ""))
    if path is None or not path.exists():
        clear_spooled_df(namespace, safe_query_id, remove_file=False)
        return None
    return str(path)


def register_spool_file(
    namespace: str,
    query_id: str,
    src_path: "Path",
    row_count: int,
    *,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """Register an already-written parquet file in the spool metadata store.

    Moves *src_path* to the canonical spool location and creates the Redis
    metadata pointer. Returns True on success. This avoids reloading the full
    DataFrame into memory (use after streaming writes via ParquetWriter).
    """
    if not QUERY_SPOOL_ENABLED:
        return False

    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        logger.warning("Invalid query_id for register_spool_file: %s", query_id)
        return False

    client = get_redis_client()
    if client is None:
        logger.warning("Redis unavailable, skip register_spool_file for query_id=%s", safe_query_id)
        return False

    ttl = max(int(ttl_seconds or QUERY_SPOOL_TTL_SECONDS), 60)

    try:
        import pyarrow.parquet as _pq
        schema = _pq.read_schema(str(src_path))
        columns = [str(f.name) for f in schema]
    except Exception:
        columns = []

    try:
        dest = _target_path(namespace, safe_query_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _move_into_place(Path(src_path), dest)

        now_ts = int(time.time())
        metadata = {
            "schema_version": _SPOOL_SCHEMA_VERSION,
            "namespace": _normalize_namespace(namespace),
            "query_id": safe_query_id,
            "relative_path": str(dest.relative_to(_spool_root())),
            "row_count": int(row_count),
            "column_count": int(len(columns)),
            "columns_hash": _columns_hash(columns),
            "created_at": now_ts,
            "expires_at": now_ts + ttl,
            "file_size_bytes": int(dest.stat().st_size),
        }
        client.setex(
            get_key(_meta_key(namespace, safe_query_id)),
            ttl,
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        )
        return True
    except Exception as exc:
        logger.warning("Failed to register spool file (query_id=%s): %s", safe_query_id, exc)
        return False


def register_stage_spool_file(
    namespace: str,
    query_id: str,
    stage: str,
    src_path: "Path",
    row_count: int,
    *,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """Register a stage-level parquet file for a multi-stage pipeline job.

    Stores the file at ``{namespace}/{query_id}_{stage}.parquet`` and records
    both per-stage metadata (``{ns}:spool_stage:{query_id}:{stage}``) and a
    Redis SET index of completed stages (``{ns}:spool_stages:{query_id}``).
    """
    if not QUERY_SPOOL_ENABLED:
        return False

    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        logger.warning("Invalid query_id for register_stage_spool_file: %s", query_id)
        return False

    safe_st = _safe_stage(stage)
    client = get_redis_client()
    if client is None:
        logger.warning("Redis unavailable, skip register_stage_spool_file query_id=%s stage=%s", safe_query_id, safe_st)
        return False

    ttl = max(int(ttl_seconds or QUERY_SPOOL_TTL_SECONDS), 60)

    try:
        import pyarrow.parquet as _pq
        schema = _pq.read_schema(str(src_path))
        columns = [str(f.name) for f in schema]
    except Exception:
        columns = []

    try:
        dest = _stage_target_path(namespace, safe_query_id, safe_st)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _move_into_place(Path(src_path), dest)

        now_ts = int(time.time())
        metadata = {
            "schema_version": _SPOOL_SCHEMA_VERSION,
            "namespace": _normalize_namespace(namespace),
            "query_id": safe_query_id,
            "stage": safe_st,
            "relative_path": str(dest.relative_to(_spool_root())),
            "row_count": int(row_count),
            "column_count": int(len(columns)),
            "columns_hash": _columns_hash(columns),
            "created_at": now_ts,
            "expires_at": now_ts + ttl,
            "file_size_bytes": int(dest.stat().st_size),
        }
        stage_key = get_key(_stage_meta_key(namespace, safe_query_id, safe_st))
        client.setex(stage_key, ttl, json.dumps(metadata, ensure_ascii=False, sort_keys=True))

        # Track stage name in the namespace index SET
        index_key = get_key(_stage_index_key(namespace, safe_query_id))
        client.sadd(index_key, safe_st)
        client.expire(index_key, ttl)

        return True
    except Exception as exc:
        logger.warning(
            "Failed to register stage spool file (query_id=%s stage=%s): %s",
            safe_query_id, safe_st, exc,
        )
        return False


def get_stage_spool_metadata(namespace: str, query_id: str, stage: str) -> Optional[dict]:
    """Return metadata for a specific stage of a multi-stage spool."""
    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        return None
    client = get_redis_client()
    if client is None:
        return None
    key = get_key(_stage_meta_key(namespace, safe_query_id, _safe_stage(stage)))
    try:
        raw = client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Failed to read stage spool metadata for %s/%s: %s", safe_query_id, stage, exc)
        return None


def get_stage_spool_path(namespace: str, query_id: str, stage: str) -> Optional[str]:
    """Resolve the parquet file path for a specific stage without loading it."""
    if not QUERY_SPOOL_ENABLED:
        return None
    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        return None
    metadata = get_stage_spool_metadata(namespace, safe_query_id, stage)
    if metadata is None:
        return None
    expires_at = int(metadata.get("expires_at") or 0)
    if expires_at and expires_at <= int(time.time()):
        return None
    path = _path_from_relative(str(metadata.get("relative_path") or ""))
    if path is None or not path.exists():
        return None
    return str(path)


def list_namespace_stages(namespace: str, query_id: str) -> list:
    """Return the list of completed stage names for a multi-stage spool."""
    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        return []
    client = get_redis_client()
    if client is None:
        return []
    key = get_key(_stage_index_key(namespace, safe_query_id))
    try:
        members = client.smembers(key)
        return sorted(m.decode() if isinstance(m, bytes) else str(m) for m in members)
    except Exception:
        return []


def list_namespace_spool_paths(namespace: str, query_id: str) -> list:
    """Return resolved parquet file paths for all completed stages."""
    stages = list_namespace_stages(namespace, query_id)
    paths = []
    for stage in stages:
        path = get_stage_spool_path(namespace, query_id, stage)
        if path:
            paths.append(path)
    return paths


def clear_spooled_df(namespace: str, query_id: str, *, remove_file: bool = True) -> None:
    safe_query_id = _safe_query_id(query_id)
    if not safe_query_id:
        return
    client = get_redis_client()
    key = get_key(_meta_key(namespace, safe_query_id))

    if remove_file:
        metadata = get_spool_metadata(namespace, safe_query_id)
        rel = str((metadata or {}).get("relative_path") or "")
        path = _path_from_relative(rel) if rel else None
        if path and path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    if client is not None:
        try:
            client.delete(key)
        except Exception:
            pass


def cleanup_expired_spool(namespace: str | None = None) -> dict[str, int]:
    """Cleanup expired metadata and orphan parquet files."""
    stats = {
        "meta_checked": 0,
        "meta_deleted": 0,
        "expired_files_deleted": 0,
        "orphan_files_deleted": 0,
        "spool_bytes": 0,
    }
    root = _spool_root()
    root.mkdir(parents=True, exist_ok=True)

    referenced_paths: set[str] = set()
    now_ts = int(time.time())
    client = get_redis_client()
    if client is not None:
        if namespace:
            pattern = get_key(f"{_normalize_namespace(namespace)}:spool_meta:*")
        else:
            pattern = get_key("*:spool_meta:*")
        try:
            for key in client.scan_iter(match=pattern, count=200):
                stats["meta_checked"] += 1
                raw = client.get(key)
                if not raw:
                    continue
                try:
                    meta = json.loads(raw)
                except Exception:
                    client.delete(key)
                    stats["meta_deleted"] += 1
                    continue
                rel = str(meta.get("relative_path") or "")
                path = _path_from_relative(rel) if rel else None
                expires_at = int(meta.get("expires_at") or 0)
                expired = bool(expires_at and expires_at <= now_ts)
                missing = path is None or not path.exists()
                if expired or missing:
                    if path is not None and path.exists():
                        try:
                            path.unlink()
                            stats["expired_files_deleted"] += 1
                        except OSError:
                            pass
                    client.delete(key)
                    stats["meta_deleted"] += 1
                elif path is not None:
                    referenced_paths.add(str(path))
        except Exception as exc:
            logger.warning("Spool metadata cleanup failed: %s", exc)

        # Also protect stage spool files from orphan deletion.
        # Stage spools only have spool_stage keys (not spool_meta), so without
        # this scan they would be treated as orphans and deleted prematurely.
        if namespace:
            stage_pattern = get_key(f"{_normalize_namespace(namespace)}:spool_stage:*")
        else:
            stage_pattern = get_key("*:spool_stage:*")
        try:
            for key in client.scan_iter(match=stage_pattern, count=200):
                raw = client.get(key)
                if not raw:
                    continue
                try:
                    meta = json.loads(raw)
                except Exception:
                    client.delete(key)
                    continue
                rel = str(meta.get("relative_path") or "")
                path = _path_from_relative(rel) if rel else None
                expires_at = int(meta.get("expires_at") or 0)
                expired = bool(expires_at and expires_at <= now_ts)
                missing = path is None or not path.exists()
                if expired or missing:
                    if path is not None and path.exists():
                        try:
                            path.unlink()
                            stats["expired_files_deleted"] += 1
                        except OSError:
                            pass
                    client.delete(key)
                    stats["meta_deleted"] += 1
                elif path is not None:
                    referenced_paths.add(str(path))
        except Exception as exc:
            logger.warning("Stage spool metadata cleanup failed: %s", exc)

    for file_path in root.rglob("*.parquet"):
        resolved = str(file_path.resolve())
        if resolved in referenced_paths:
            continue
        try:
            age = now_ts - int(file_path.stat().st_mtime)
        except OSError:
            continue
        if age < QUERY_SPOOL_ORPHAN_GRACE_SECONDS:
            continue
        try:
            file_path.unlink()
            stats["orphan_files_deleted"] += 1
        except OSError:
            continue

    for candidate in sorted(root.rglob("*"), reverse=True):
        if candidate.is_dir():
            try:
                candidate.rmdir()
            except OSError:
                pass

    stats["spool_bytes"] = _get_spool_size_bytes()
    return stats


def _worker_loop() -> None:
    logger.info(
        "Query spool cleanup worker started (interval=%ss)",
        QUERY_SPOOL_CLEANUP_INTERVAL_SECONDS,
    )
    while not _STOP_EVENT.wait(QUERY_SPOOL_CLEANUP_INTERVAL_SECONDS):
        try:
            if try_acquire_lock(_CLEANUP_LOCK_NAME, ttl_seconds=120, fail_mode="raise"):
                try:
                    cleanup_expired_spool(namespace=None)
                finally:
                    release_lock(_CLEANUP_LOCK_NAME)
        except LockUnavailableError as exc:
            logger.warning("Query spool cleanup skipped: Redis unavailable (%s)", exc)
        except Exception as exc:
            logger.warning("Query spool cleanup failed: %s", exc)
    logger.info("Query spool cleanup worker stopped")


def init_query_spool_cleanup(app=None) -> None:
    """Initialize spool directory and start periodic cleanup worker."""
    if not QUERY_SPOOL_ENABLED:
        return
    cleanup_expired_spool(namespace=None)

    global _WORKER_THREAD
    if app is not None and app.config.get("TESTING"):
        return
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    _WORKER_THREAD = threading.Thread(
        target=_worker_loop,
        daemon=True,
        name="query-spool-cleanup",
    )
    _WORKER_THREAD.start()


def stop_query_spool_cleanup_worker(timeout: int = 5) -> None:
    global _WORKER_THREAD
    if _WORKER_THREAD is None:
        return
    _STOP_EVENT.set()
    _WORKER_THREAD.join(timeout=timeout)
    _WORKER_THREAD = None


# ============================================================
# Canonical Query Identity Contract
# ============================================================

_VALID_DOMAIN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def make_canonical_query_id(domain: str, params: dict[str, Any]) -> str:
    """Derive a deterministic canonical query identity from domain + params.

    The identity is a stable SHA-256-based hex string that uniquely
    identifies a (domain, parameter-set) pair.  Callers should canonicalize
    *params* before hashing (sort keys, normalize types).

    Args:
        domain: Short domain label (e.g. "reject", "material_trace").
        params: Dict of query parameters that define the query identity.

    Returns:
        32-character hex string suitable for use as a spool query_id.
    """
    domain_safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(domain or "unknown").strip()) or "unknown"
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=True, default=str)
    payload = f"{domain_safe}:{canonical}"
    return f"{domain_safe}." + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


# ============================================================
# Inflight State Contract
# ============================================================

_INFLIGHT_KEY_TTL_SECONDS = 300  # default inflight state TTL


def _inflight_key(namespace: str, query_id: str) -> str:
    ns = _normalize_namespace(namespace)
    return f"{ns}:inflight:{query_id}"


def set_inflight_state(
    namespace: str,
    query_id: str,
    state: dict[str, Any],
    *,
    ttl_seconds: int = _INFLIGHT_KEY_TTL_SECONDS,
) -> bool:
    """Publish lightweight inflight state for a running heavy-query job.

    Redis stores only control-plane metadata (job_id, status, worker, etc.),
    never the result body.

    Args:
        namespace: Spool namespace (matches the spool namespace for this domain).
        query_id: Canonical query identity.
        state: Dict of inflight metadata (job_id, status, started_at, …).
        ttl_seconds: State expiry; should exceed expected job duration.

    Returns:
        True if saved to Redis successfully.
    """
    safe_id = _safe_query_id(query_id)
    if not safe_id:
        return False
    client = get_control_redis_client()
    if client is None:
        return False
    key = get_key(_inflight_key(namespace, safe_id))
    try:
        payload = json.dumps(state, ensure_ascii=False, default=str)
        client.setex(key, max(int(ttl_seconds), 10), payload)
        return True
    except Exception as exc:
        logger.warning("Failed to set inflight state for %s: %s", safe_id, exc)
        return False


def get_inflight_state(namespace: str, query_id: str) -> Optional[dict[str, Any]]:
    """Return current inflight state for a running heavy-query job, or None."""
    safe_id = _safe_query_id(query_id)
    if not safe_id:
        return None
    client = get_control_redis_client()
    if client is None:
        return None
    key = get_key(_inflight_key(namespace, safe_id))
    try:
        raw = client.get(key)
        if not raw:
            return None
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Failed to get inflight state for %s: %s", safe_id, exc)
        return None


def clear_inflight_state(namespace: str, query_id: str) -> None:
    """Remove inflight state when a job completes or fails."""
    safe_id = _safe_query_id(query_id)
    if not safe_id:
        return
    client = get_control_redis_client()
    if client is None:
        return
    key = get_key(_inflight_key(namespace, safe_id))
    try:
        client.delete(key)
    except Exception as exc:
        logger.warning("Failed to clear inflight state for %s: %s", safe_id, exc)


# ============================================================
# Spool Metadata Status Helpers
# ============================================================

def update_spool_status(namespace: str, query_id: str, status: str) -> bool:
    """Patch the status field on an existing spool metadata record.

    Does not change TTL or any other metadata field.  Returns False if the
    metadata key is missing or Redis is unavailable.

    Args:
        namespace: Spool namespace.
        query_id: Canonical query identity.
        status: New status string (use constants from cache_plane module).
    """
    safe_id = _safe_query_id(query_id)
    if not safe_id:
        return False
    client = get_redis_client()
    if client is None:
        return False
    key = get_key(_meta_key(namespace, safe_id))
    try:
        raw = client.get(key)
        if not raw:
            return False
        metadata = json.loads(raw)
        if not isinstance(metadata, dict):
            return False
        metadata["status"] = str(status)
        # Preserve remaining TTL
        remaining_ttl = client.ttl(key)
        if remaining_ttl is None or remaining_ttl <= 0:
            remaining_ttl = QUERY_SPOOL_TTL_SECONDS
        client.setex(key, int(remaining_ttl), json.dumps(metadata, ensure_ascii=False, sort_keys=True))
        return True
    except Exception as exc:
        logger.warning("Failed to update spool status for %s: %s", safe_id, exc)
        return False
