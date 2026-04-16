#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orphan job reaper.

Scans Redis for async job metadata keys that have been stuck in an active
state (queued / running / started) for longer than a configurable grace
period, marks them as failed, and deletes stale Parquet spool files on
disk.

Usage:
    conda run -n mes-dashboard python scripts/reap_orphan_jobs.py [--dry-run]

Options:
    --dry-run   Print what would be reaped without writing any changes.

Exit codes:
    0   Normal completion (even if nothing was reaped).
    1   Fatal error (Redis unreachable, etc.).

Redis key pattern (from async_query_job_service.py):
    {REDIS_KEY_PREFIX}:{prefix}:job:{job_id}:meta   (HSET)

Environment variables read from .env (if present) or the process env:
    REDIS_URL           Redis connection URL (default redis://localhost:6379/0)
    REDIS_KEY_PREFIX    Key namespace prefix  (default mes_wip)
    QUERY_SPOOL_DIR     Spool directory path  (default tmp/query_spool)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: load .env before importing app modules so that the Redis /
# spool config is available even when running outside the Flask context.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.is_file():
    with _ENV_FILE.open() as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _value = _line.split("=", 1)
            if "#" in _value:
                _value = _value[: _value.index("#")]
            os.environ.setdefault(_key.strip(), _value.strip())

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_KEY_PREFIX: str = os.getenv("REDIS_KEY_PREFIX", "mes_wip")

# Jobs stuck in an active state longer than this are reaped (seconds).
ORPHAN_JOB_AGE_SECONDS: int = int(os.getenv("ORPHAN_JOB_AGE_SECONDS", str(2 * 3600)))

# Spool files older than this are deleted (seconds).
SPOOL_FILE_MAX_AGE_SECONDS: int = int(os.getenv("SPOOL_FILE_MAX_AGE_SECONDS", str(24 * 3600)))

# The spool directory.  Mirrors the value in query_spool_store.py.
# Use an absolute path if provided; otherwise resolve relative to project root.
_spool_dir_raw = os.getenv("QUERY_SPOOL_DIR", "tmp/query_spool")
SPOOL_DIR: Path = (
    Path(_spool_dir_raw)
    if Path(_spool_dir_raw).is_absolute()
    else (_PROJECT_ROOT / _spool_dir_raw)
).resolve()

# Active statuses that qualify a job as an orphan candidate.
_ACTIVE_STATUSES: frozenset[str] = frozenset({"queued", "running", "started"})

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connect_redis():
    """Return a Redis client or raise SystemExit on failure."""
    try:
        import redis
    except ImportError:
        print("ERROR: redis-py is not installed in this environment.", file=sys.stderr)
        sys.exit(1)

    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception as exc:
        print(f"ERROR: Cannot connect to Redis at {REDIS_URL}: {exc}", file=sys.stderr)
        sys.exit(1)


def _scan_job_meta_keys(client) -> list[str]:
    """Return all keys matching the job metadata pattern.

    Pattern: {prefix}:*:job:*:meta
    The leading {prefix}: is the REDIS_KEY_PREFIX.
    """
    pattern = f"{REDIS_KEY_PREFIX}:*:job:*:meta"
    keys: list[str] = []
    cursor = 0
    while True:
        cursor, batch = client.scan(cursor, match=pattern, count=200)
        keys.extend(batch)
        if cursor == 0:
            break
    return keys


def _reap_orphan_jobs(client, dry_run: bool) -> dict:
    """Scan and reap orphan jobs.  Returns a summary dict."""
    now = time.time()
    keys = _scan_job_meta_keys(client)
    total_scanned = len(keys)
    reaped: list[str] = []
    skipped: list[str] = []

    for key in keys:
        try:
            meta = client.hgetall(key)
        except Exception as exc:
            print(f"  WARN: Could not read key {key}: {exc}")
            skipped.append(key)
            continue

        status = meta.get("status", "")
        if status not in _ACTIVE_STATUSES:
            continue

        created_at_raw = meta.get("created_at", "0")
        try:
            created_at = float(created_at_raw)
        except (TypeError, ValueError):
            created_at = 0.0

        age_seconds = now - created_at if created_at > 0 else float("inf")
        if age_seconds < ORPHAN_JOB_AGE_SECONDS:
            continue

        # This job is an orphan.
        job_id = meta.get("job_id", key)
        age_h = age_seconds / 3600
        print(
            f"  REAP job_id={job_id!r} status={status!r} "
            f"age={age_h:.1f}h key={key}"
        )
        reaped.append(key)

        if not dry_run:
            try:
                client.hset(
                    key,
                    mapping={
                        "status": "failed",
                        "error": "reaped by orphan cleanup",
                        "reaped_at": str(now),
                    },
                )
            except Exception as exc:
                print(f"  WARN: Could not update key {key}: {exc}")

    return {
        "total_scanned": total_scanned,
        "reaped": len(reaped),
        "skipped": len(skipped),
    }


def _reap_stale_spool_files(dry_run: bool) -> dict:
    """Delete Parquet spool files older than SPOOL_FILE_MAX_AGE_SECONDS."""
    deleted: list[Path] = []
    errors: list[str] = []

    if not SPOOL_DIR.exists():
        return {"total_found": 0, "deleted": 0, "errors": 0, "dir": str(SPOOL_DIR)}

    now = time.time()
    parquet_files = list(SPOOL_DIR.rglob("*.parquet"))
    total_found = len(parquet_files)

    for fpath in parquet_files:
        try:
            mtime = fpath.stat().st_mtime
        except OSError:
            continue

        age_seconds = now - mtime
        if age_seconds < SPOOL_FILE_MAX_AGE_SECONDS:
            continue

        age_h = age_seconds / 3600
        print(f"  DELETE {fpath.name} age={age_h:.1f}h path={fpath}")
        deleted.append(fpath)

        if not dry_run:
            try:
                fpath.unlink()
            except OSError as exc:
                print(f"  WARN: Could not delete {fpath}: {exc}")
                errors.append(str(fpath))

    return {
        "total_found": total_found,
        "deleted": len(deleted),
        "errors": len(errors),
        "dir": str(SPOOL_DIR),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reap orphan async jobs and stale spool files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be reaped without making any changes.",
    )
    args = parser.parse_args()
    dry_run: bool = args.dry_run

    if dry_run:
        print("=== DRY RUN — no changes will be written ===\n")

    print(f"Redis URL     : {REDIS_URL}")
    print(f"Key prefix    : {REDIS_KEY_PREFIX}")
    print(f"Job age limit : {ORPHAN_JOB_AGE_SECONDS}s ({ORPHAN_JOB_AGE_SECONDS / 3600:.1f}h)")
    print(f"Spool max age : {SPOOL_FILE_MAX_AGE_SECONDS}s ({SPOOL_FILE_MAX_AGE_SECONDS / 3600:.1f}h)")
    print(f"Spool dir     : {SPOOL_DIR}\n")

    # --- Phase 1: orphan job reaping ---
    print("Phase 1: scanning Redis for orphan jobs …")
    client = _connect_redis()
    job_summary = _reap_orphan_jobs(client, dry_run=dry_run)
    print(
        f"  scanned={job_summary['total_scanned']} "
        f"reaped={job_summary['reaped']} "
        f"skipped={job_summary['skipped']}\n"
    )

    # --- Phase 2: stale spool file cleanup ---
    print("Phase 2: scanning spool directory for stale Parquet files …")
    spool_summary = _reap_stale_spool_files(dry_run=dry_run)
    print(
        f"  dir={spool_summary['dir']} "
        f"found={spool_summary['total_found']} "
        f"deleted={spool_summary['deleted']} "
        f"errors={spool_summary['errors']}\n"
    )

    # --- Summary ---
    print("=== Summary ===")
    print(f"Orphan jobs reaped : {job_summary['reaped']}")
    print(f"Spool files deleted: {spool_summary['deleted']}")
    if dry_run:
        print("(dry-run — no changes written)")


if __name__ == "__main__":
    main()
