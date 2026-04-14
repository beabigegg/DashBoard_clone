#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Capture real-DB chunk snapshots for spool replay tests.

Runs a service-layer query end-to-end against live Oracle + Redis, tees each
chunk yielded by ``iterate_chunks`` to disk, and writes a ``meta.json`` so
``tests/test_spool_replay.py`` can replay the exact chunk sequence offline.

Usage
-----
    # Activate the conda env first, then:
    python scripts/capture_spool_snapshot.py job \\
        --label non_prod_eqp_halfyear \\
        --resource-ids EQP-NONPROD-A,EQP-NONPROD-B \\
        --start 2025-09-01 --end 2026-03-31

    python scripts/capture_spool_snapshot.py resource \\
        --label halfyear_nonprod \\
        --start 2025-09-01 --end 2026-03-31 \\
        --resource-ids EQP-NONPROD-A

Snapshots land under ``tests/fixtures/spool_snapshots/<prefix>__<label>/``
(gitignored) and are auto-discovered by ``test_spool_replay.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List

import pandas as pd

# Resolve repo root + ensure src/ on path (script may run from anywhere)
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

SNAPSHOT_ROOT = REPO_ROOT / "tests" / "fixtures" / "spool_snapshots"


@contextmanager
def tee_iterate_chunks(target_prefix: str, target_hash_ref: Dict[str, str], out_dir: Path):
    """Wrap ``batch_query_engine.iterate_chunks`` to dump each chunk to *out_dir*.

    Only chunks whose ``cache_prefix`` matches *target_prefix* are captured, so a
    service that dispatches multiple prefixes (e.g. resource + resource_oee) can
    be captured one at a time without cross-contamination.

    ``target_hash_ref`` is a mutable dict the caller can read after exit to
    learn the actual ``query_hash`` the service picked — handy for meta.json.
    """
    import mes_dashboard.services.batch_query_engine as bqe

    out_dir.mkdir(parents=True, exist_ok=True)
    original = bqe.iterate_chunks
    captured: List[Dict] = []

    def _wrapped(cache_prefix, query_hash, *a, **kw):
        if cache_prefix != target_prefix:
            yield from original(cache_prefix, query_hash, *a, **kw)
            return

        target_hash_ref["query_hash"] = query_hash
        for i, chunk in enumerate(original(cache_prefix, query_hash, *a, **kw)):
            # Persist every chunk including empty ones so replay sees the
            # exact same sequence length the merge path saw.
            chunk_path = out_dir / f"chunk_{i:04d}.parquet"
            try:
                chunk.to_parquet(chunk_path, engine="pyarrow", index=False)
            except Exception as exc:  # pragma: no cover - diagnostic
                print(f"  ! failed to dump chunk {i}: {exc}", file=sys.stderr)
                raise
            captured.append({
                "index": i,
                "rows": int(len(chunk)),
                "columns": list(chunk.columns),
                "dtypes": {c: str(chunk[c].dtype) for c in chunk.columns},
                "file": chunk_path.name,
            })
            yield chunk

    bqe.iterate_chunks = _wrapped
    try:
        yield captured
    finally:
        bqe.iterate_chunks = original


def _write_meta(out_dir: Path, *, prefix: str, label: str, params: dict,
                query_hash: str, captured: List[Dict]) -> None:
    meta = {
        "cache_prefix": prefix,
        "label": label,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "query_hash": query_hash,
        "params": params,
        "chunk_count": len(captured),
        "total_rows": sum(c["rows"] for c in captured),
        "chunks": captured,
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


# ------------------------------------------------------------------
# Per-prefix capture functions
# ------------------------------------------------------------------


def capture_job(args) -> None:
    from mes_dashboard.services.job_query_service import get_jobs_by_resources

    resource_ids = [r.strip() for r in args.resource_ids.split(",") if r.strip()]
    params = {
        "resource_ids": resource_ids,
        "start_date": args.start,
        "end_date": args.end,
    }
    out_dir = SNAPSHOT_ROOT / f"job__{args.label}"
    hash_ref: Dict[str, str] = {}

    print(f"[job] calling get_jobs_by_resources({params})")
    with tee_iterate_chunks("job", hash_ref, out_dir) as captured:
        result = get_jobs_by_resources(**params)

    if isinstance(result, dict) and "error" in result:
        print(f"  ! service returned error: {result['error']}", file=sys.stderr)
    if not captured:
        print("  ! no chunks captured — date range may be below the "
              "BATCH_QUERY_TIME_THRESHOLD_DAYS threshold (engine not activated)",
              file=sys.stderr)

    _write_meta(out_dir, prefix="job", label=args.label, params=params,
                query_hash=hash_ref.get("query_hash", ""), captured=captured)
    print(f"[job] captured {len(captured)} chunks -> {out_dir}")


def capture_resource(args) -> None:
    from mes_dashboard.services.resource_dataset_cache import execute_primary_query

    resource_ids = [r.strip() for r in (args.resource_ids or "").split(",") if r.strip()]
    params = {
        "start_date": args.start,
        "end_date": args.end,
        "granularity": args.granularity,
        "resource_ids": resource_ids or None,
        "is_production": args.is_production,
    }
    out_dir = SNAPSHOT_ROOT / f"resource__{args.label}"
    hash_ref: Dict[str, str] = {}

    print(f"[resource] calling execute_primary_query({params})")
    with tee_iterate_chunks("resource", hash_ref, out_dir) as captured:
        execute_primary_query(**params)

    _write_meta(out_dir, prefix="resource", label=args.label, params=params,
                query_hash=hash_ref.get("query_hash", ""), captured=captured)
    print(f"[resource] captured {len(captured)} chunks -> {out_dir}")


CAPTURE_DISPATCH: Dict[str, Callable] = {
    "job": capture_job,
    "resource": capture_resource,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="prefix", required=True)

    job = sub.add_parser("job", help="capture job_query_service.get_jobs_by_resources")
    job.add_argument("--label", required=True, help="snapshot label (dir suffix)")
    job.add_argument("--resource-ids", required=True, help="comma-separated RESOURCEID list")
    job.add_argument("--start", required=True, help="YYYY-MM-DD (wide enough to trigger engine)")
    job.add_argument("--end", required=True, help="YYYY-MM-DD")

    res = sub.add_parser("resource", help="capture resource_dataset_cache.execute_primary_query")
    res.add_argument("--label", required=True)
    res.add_argument("--start", required=True)
    res.add_argument("--end", required=True)
    res.add_argument("--granularity", default="day", choices=["day", "hour"])
    res.add_argument("--resource-ids", default="", help="optional comma-separated filter")
    res.add_argument("--is-production", action="store_true")

    return p


def main() -> int:
    args = build_parser().parse_args()
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    fn = CAPTURE_DISPATCH[args.prefix]
    fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
