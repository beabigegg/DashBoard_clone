# -*- coding: utf-8 -*-
"""Replay real-DB chunk snapshots through ``merge_chunks_to_spool``.

Snapshots are captured locally via ``scripts/capture_spool_snapshot.py`` into
``tests/fixtures/spool_snapshots/`` (gitignored). This test auto-discovers every
snapshot directory and replays its chunks through the merge pipeline using a
mocked ``iterate_chunks``. It gives us characterization coverage against actual
Oracle data shapes — the exact failure mode (null-typed column inference, Arrow
cast failures, empty edge cases) that property-based fuzzing approximates but
doesn't guarantee.

If no snapshots are present (e.g. fresh clone, CI), the test module collects
a single ``test_no_snapshots_is_ok`` that passes — CI stays green, local devs
get coverage when they capture.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

import mes_dashboard.services.batch_query_engine as bqe

SNAPSHOT_ROOT = Path(__file__).resolve().parent / "fixtures" / "spool_snapshots"


def _discover_snapshots() -> list:
    if not SNAPSHOT_ROOT.exists():
        return []
    snapshots = []
    for sub in sorted(SNAPSHOT_ROOT.iterdir()):
        if not sub.is_dir():
            continue
        meta_path = sub / "meta.json"
        if not meta_path.exists():
            continue
        snapshots.append(sub)
    return snapshots


_SNAPSHOTS = _discover_snapshots()


def test_no_snapshots_is_ok():
    """Sanity: the replay test module loads even with no snapshots present."""
    # If snapshots exist, this still passes — it just doesn't assert anything
    # about them (the parametrized tests below handle that).
    assert SNAPSHOT_ROOT.parent.exists(), "tests/fixtures/ must exist"


def _load_meta(snapshot_dir: Path) -> dict:
    return json.loads((snapshot_dir / "meta.json").read_text(encoding="utf-8"))


def _load_chunks(snapshot_dir: Path, meta: dict) -> list:
    chunks = []
    for chunk_meta in meta["chunks"]:
        path = snapshot_dir / chunk_meta["file"]
        chunks.append(pd.read_parquet(path, engine="pyarrow"))
    return chunks


@pytest.mark.skipif(not _SNAPSHOTS, reason="no local spool snapshots captured")
@pytest.mark.parametrize("snapshot_dir", _SNAPSHOTS, ids=lambda p: p.name)
def test_replay_snapshot_merges_successfully(snapshot_dir: Path, tmp_path):
    """For each captured snapshot: merge chunks → parquet, assert invariants.

    Invariants checked against meta.json ground truth:
    * Merge does not raise (would catch any regression in null/schema handling).
    * Returned row count == sum of chunk row counts in meta.
    * Parquet on disk has that same row count.
    * Every expected column is present in the output.
    """
    meta = _load_meta(snapshot_dir)
    chunks = _load_chunks(snapshot_dir, meta)

    expected_rows = meta["total_rows"]
    prefix = meta["cache_prefix"]

    with patch.object(bqe, "iterate_chunks", return_value=iter(chunks)):
        path, total = bqe.merge_chunks_to_spool(
            prefix, f"replay_{snapshot_dir.name}", spool_dir=tmp_path,
        )

    assert total == expected_rows, (
        f"row count mismatch: meta={expected_rows}, merge returned {total}"
    )

    if expected_rows == 0:
        assert path is None
        return

    assert path is not None and path.exists()
    df = pd.read_parquet(path, engine="pyarrow")
    assert len(df) == expected_rows

    # Column-set invariant: first non-empty chunk defines expected columns.
    for chunk_meta in meta["chunks"]:
        if chunk_meta["rows"] > 0:
            expected_cols = set(chunk_meta["columns"])
            break
    else:
        expected_cols = set()
    missing = expected_cols - set(df.columns)
    assert not missing, f"columns missing in merged output: {missing}"


def _pick_string_victim_column(chunk: pd.DataFrame) -> str | None:
    """Return a string-ish column suitable for forcing to all-None.

    Prefers columns whose name suggests optional diagnostic text (CAUSECODENAME,
    REPAIRCODENAME, COMMENT, *NAME) so the synthetic pattern matches real bugs.
    """
    string_cols = [
        c for c in chunk.columns
        if pd.api.types.is_string_dtype(chunk[c]) or chunk[c].dtype == object
    ]
    if not string_cols:
        return None
    # Prefer diagnostic/optional fields the known bugs hit
    for pref in ("CAUSECODENAME", "REPAIRCODENAME", "SYMPTOMCODENAME", "RELEASECOMMENTS"):
        if pref in string_cols:
            return pref
    # Fallback: any column ending in NAME/COMMENT
    for c in string_cols:
        if c.endswith("NAME") or "COMMENT" in c:
            return c
    return string_cols[0]


@pytest.mark.skipif(not _SNAPSHOTS, reason="no local spool snapshots captured")
@pytest.mark.parametrize("snapshot_dir", _SNAPSHOTS, ids=lambda p: p.name)
def test_replay_snapshot_null_promotion_synthesis(snapshot_dir: Path, tmp_path):
    """Force the exact null-promotion bug pattern onto a real snapshot.

    Recipe:
    1. Find the first non-empty chunk with real string data in any column.
    2. Force that column to all-None in that chunk (triggers PyArrow null-type
       inference when it's the first chunk).
    3. Put it as chunk 0; keep subsequent chunks with real string values.
    4. Assert merge succeeds and the null rows survive round-trip as NaN while
       string rows keep their values.

    This test exercises the *actual* Oracle column set + dtypes for each
    prefix, rather than a hand-crafted schema — catching cases where real
    column names/types diverge from what the synthetic property tests assume.

    Skips when the snapshot has no non-empty chunk with string columns (e.g.
    the GTMA-0121 all-empty case).
    """
    meta = _load_meta(snapshot_dir)
    chunks = _load_chunks(snapshot_dir, meta)

    # Find first non-empty chunk with at least one non-null value in some string col
    donor_idx = None
    victim_col = None
    for i, c in enumerate(chunks):
        if c.empty:
            continue
        col = _pick_string_victim_column(c)
        if col is None:
            continue
        if c[col].notna().any():
            donor_idx = i
            victim_col = col
            break
    if donor_idx is None:
        pytest.skip(f"{snapshot_dir.name}: no non-empty chunk with string data to synthesize null-promotion")

    # Build synthetic sequence: donor_null (all None in victim) → donor (real strings)
    donor = chunks[donor_idx].copy()
    donor_null = donor.copy()
    donor_null[victim_col] = None

    synthetic_chunks = [donor_null, donor]
    expected_rows = len(donor_null) + len(donor)

    with patch.object(bqe, "iterate_chunks", return_value=iter(synthetic_chunks)):
        path, total = bqe.merge_chunks_to_spool(
            meta["cache_prefix"],
            f"nullpromo_{snapshot_dir.name}",
            spool_dir=tmp_path,
        )

    assert total == expected_rows, \
        f"null-promotion merge row count mismatch: expected {expected_rows}, got {total}"
    assert path is not None and path.exists()

    out = pd.read_parquet(path, engine="pyarrow")
    assert len(out) == expected_rows
    # First len(donor_null) rows: victim column must be NaN
    assert out[victim_col].iloc[:len(donor_null)].isna().all(), \
        f"null-promotion lost null markers in first chunk (col={victim_col})"
    # Rows from real donor: must preserve original non-null count
    original_non_null = int(donor[victim_col].notna().sum())
    restored_non_null = int(out[victim_col].iloc[len(donor_null):].notna().sum())
    assert restored_non_null == original_non_null, \
        f"null-promotion corrupted donor rows: {restored_non_null}/{original_non_null} non-null survived"


@pytest.mark.skipif(not _SNAPSHOTS, reason="no local spool snapshots captured")
@pytest.mark.parametrize("snapshot_dir", _SNAPSHOTS, ids=lambda p: p.name)
def test_replay_snapshot_rejects_column_drift(snapshot_dir: Path, tmp_path):
    """Inject a synthetic column into the last chunk — merge MUST raise.

    Guards the newly-landed ``ChunkSchemaMismatch`` contract against regressions
    that could reintroduce the silent ``common_cols`` fallback.
    """
    meta = _load_meta(snapshot_dir)
    chunks = _load_chunks(snapshot_dir, meta)

    non_empty = [i for i, c in enumerate(chunks) if not c.empty]
    if len(non_empty) < 2:
        pytest.skip("need at least 2 non-empty chunks to drift the second one")

    drift_idx = non_empty[-1]
    chunks[drift_idx] = chunks[drift_idx].assign(__DRIFT_COL__="x")

    with patch.object(bqe, "iterate_chunks", return_value=iter(chunks)):
        with pytest.raises(bqe.ChunkSchemaMismatch):
            bqe.merge_chunks_to_spool(
                meta["cache_prefix"],
                f"drift_{snapshot_dir.name}",
                spool_dir=tmp_path,
            )
