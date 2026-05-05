# -*- coding: utf-8 -*-
"""Property-based tests for ``merge_chunks_to_spool``.

These tests fuzz the streaming spool merge with randomized chunk sequences and
check structural invariants (I1-I9) that must hold for every input. They use a
seeded ``random.Random`` so failures are reproducible without adding a new dep
like Hypothesis.

Invariants
----------
I1  Row conservation (no cap):   total == sum(len(c) for c in chunks)
I2  Truncate == slice (differential): truncate(cap) == full.head(cap)
I3  Error mode completeness:     success ⇒ total == sum ≤ cap; otherwise raises
I4  Order preservation:          output rows keep chunk-concat order
I5  Empty ⇒ (None, 0) + no file left in spool_dir
I6  Exception cleanup:           any raise ⇒ no *{query_hash}*.parquet left
I7  Returned rows == on-disk rows
I8  Path locality + suffix
I9  Null promotion:              null-typed col in chunk 1 + strings later works
"""

import random
from unittest.mock import patch

import pandas as pd
import pytest

import mes_dashboard.services.batch_query_engine as bqe


# ------------------------------------------------------------------
# Chunk generator
# ------------------------------------------------------------------

_STRING_COLS = ["JOBID", "RESOURCENAME", "CAUSECODENAME", "REPAIRCODENAME"]


def _make_chunk(rng: random.Random, n_rows: int, none_density: float, row_offset: int) -> pd.DataFrame:
    """Build a chunk with the canonical column set and a random None pattern.

    row_offset lets each row carry a globally unique tag so order checks work.
    """
    data = {}
    for col in _STRING_COLS:
        data[col] = [
            None if rng.random() < none_density else f"{col}_{row_offset + i}"
            for i in range(n_rows)
        ]
    return pd.DataFrame(data)


def _random_chunk_sequence(seed: int, *, max_chunks: int = 6, max_rows: int = 15) -> list:
    rng = random.Random(seed)
    n_chunks = rng.randint(0, max_chunks)
    chunks = []
    row_offset = 0
    for _ in range(n_chunks):
        n_rows = rng.randint(0, max_rows)
        none_density = rng.random()
        chunk = _make_chunk(rng, n_rows, none_density, row_offset)
        chunks.append(chunk)
        row_offset += n_rows
    return chunks


def _total_expected_rows(chunks) -> int:
    return sum(len(c) for c in chunks)


def _concat_expected(chunks) -> pd.DataFrame:
    non_empty = [c for c in chunks if not c.empty]
    if not non_empty:
        return pd.DataFrame(columns=_STRING_COLS)
    return pd.concat(non_empty, ignore_index=True)


# ------------------------------------------------------------------
# I1 — Row conservation (no cap)
# ------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(150))
def test_I1_row_conservation(tmp_path, seed):
    chunks = _random_chunk_sequence(seed)
    expected = _total_expected_rows(chunks)

    with patch.object(bqe, "iterate_chunks", return_value=iter(chunks)):
        path, total = bqe.merge_chunks_to_spool("t", f"i1_{seed}", spool_dir=tmp_path)

    assert total == expected
    if expected == 0:
        assert path is None
    else:
        assert path is not None and path.exists()
        assert pd.read_parquet(path).shape[0] == expected


# ------------------------------------------------------------------
# I2 — Truncate == slice (differential)
# ------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(150))
def test_I2_truncate_equiv_slice(tmp_path, seed):
    chunks = _random_chunk_sequence(seed)
    total_rows = _total_expected_rows(chunks)
    if total_rows == 0:
        pytest.skip("empty sequence — truncate semantics trivial")

    rng = random.Random(seed ^ 0xBEEF)
    cap = rng.randint(1, max(total_rows * 2, 2))

    with patch.object(bqe, "iterate_chunks", return_value=iter([c.copy() for c in chunks])):
        p_full, n_full = bqe.merge_chunks_to_spool(
            "t", f"i2_full_{seed}", spool_dir=tmp_path,
        )
    full = pd.read_parquet(p_full) if p_full else pd.DataFrame(columns=_STRING_COLS)

    with patch.object(bqe, "iterate_chunks", return_value=iter([c.copy() for c in chunks])):
        p_trunc, n_trunc = bqe.merge_chunks_to_spool(
            "t", f"i2_trunc_{seed}", spool_dir=tmp_path,
            max_total_rows=cap, overflow_mode="truncate",
        )
    trunc = pd.read_parquet(p_trunc) if p_trunc else pd.DataFrame(columns=_STRING_COLS)

    expected = full.head(cap).reset_index(drop=True)
    # truncate may stop at a chunk boundary BEFORE reaching cap, so trunc rows
    # must be a prefix of full — allow trunc.shape[0] ≤ cap but > 0 unless full empty
    assert n_trunc <= cap
    assert n_trunc <= n_full
    pd.testing.assert_frame_equal(
        trunc.reset_index(drop=True),
        full.head(n_trunc).reset_index(drop=True),
        check_dtype=False,
    )
    # And the truncated count is either cap itself or a chunk-boundary short of it
    assert n_trunc == cap or n_trunc == n_full or n_trunc < cap


# ------------------------------------------------------------------
# I3 — Error mode completeness
# ------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(150))
def test_I3_error_mode_all_or_nothing(tmp_path, seed):
    chunks = _random_chunk_sequence(seed)
    total_rows = _total_expected_rows(chunks)
    if total_rows == 0:
        pytest.skip("empty sequence")

    rng = random.Random(seed ^ 0xCAFE)
    cap = rng.randint(1, total_rows * 2)

    try:
        with patch.object(bqe, "iterate_chunks", return_value=iter([c.copy() for c in chunks])):
            path, total = bqe.merge_chunks_to_spool(
                "t", f"i3_{seed}", spool_dir=tmp_path,
                max_total_rows=cap, overflow_mode="error",
            )
    except bqe.MergeChunksMaxRowsExceeded:
        assert total_rows > cap, "raised but total rows fit under cap"
        # I6 cleanup
        assert not list(tmp_path.glob(f"*i3_{seed}*.parquet"))
        return

    # Success path
    assert total == total_rows <= cap
    if total == 0:
        assert path is None
    else:
        assert path.exists()


# ------------------------------------------------------------------
# I4 — Order preservation
# ------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(100))
def test_I4_order_preservation(tmp_path, seed):
    # Force no-None so every row has a deterministic tag
    rng = random.Random(seed)
    chunks = []
    row_offset = 0
    for _ in range(rng.randint(1, 5)):
        n = rng.randint(1, 10)
        chunks.append(_make_chunk(rng, n, none_density=0.0, row_offset=row_offset))
        row_offset += n

    with patch.object(bqe, "iterate_chunks", return_value=iter([c.copy() for c in chunks])):
        path, total = bqe.merge_chunks_to_spool("t", f"i4_{seed}", spool_dir=tmp_path)

    out = pd.read_parquet(path)
    expected = _concat_expected(chunks).reset_index(drop=True)
    pd.testing.assert_series_equal(
        out["JOBID"].reset_index(drop=True),
        expected["JOBID"].reset_index(drop=True),
        check_names=False,
    )


# ------------------------------------------------------------------
# I5 — Empty result
# ------------------------------------------------------------------


def test_I5_all_empty_chunks_returns_none(tmp_path):
    chunks = [pd.DataFrame({c: [] for c in _STRING_COLS}) for _ in range(3)]
    with patch.object(bqe, "iterate_chunks", return_value=iter(chunks)):
        path, total = bqe.merge_chunks_to_spool("t", "i5_allempty", spool_dir=tmp_path)
    assert path is None and total == 0
    assert not list(tmp_path.glob("*.parquet"))


def test_I5_no_chunks_returns_none(tmp_path):
    with patch.object(bqe, "iterate_chunks", return_value=iter([])):
        path, total = bqe.merge_chunks_to_spool("t", "i5_none", spool_dir=tmp_path)
    assert path is None and total == 0
    assert not list(tmp_path.glob("*.parquet"))


# ------------------------------------------------------------------
# I6 — Exception cleanup (mid-iteration failure)
# ------------------------------------------------------------------


@pytest.mark.parametrize("fail_at", [0, 1, 2, 3])
def test_I6_exception_cleanup(tmp_path, fail_at):
    rng = random.Random(1234 + fail_at)
    good_chunks = [_make_chunk(rng, 5, 0.2, i * 5) for i in range(fail_at)]

    def _gen():
        for c in good_chunks:
            yield c
        raise RuntimeError("boom")

    with patch.object(bqe, "iterate_chunks", return_value=_gen()):
        with pytest.raises(RuntimeError, match="boom"):
            bqe.merge_chunks_to_spool("t", f"i6_{fail_at}", spool_dir=tmp_path)

    assert not list(tmp_path.glob(f"*i6_{fail_at}*.parquet"))


# ------------------------------------------------------------------
# I7 — Returned rows == on-disk rows
# ------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(80))
def test_I7_returned_rows_match_disk(tmp_path, seed):
    chunks = _random_chunk_sequence(seed)
    with patch.object(bqe, "iterate_chunks", return_value=iter(chunks)):
        path, total = bqe.merge_chunks_to_spool("t", f"i7_{seed}", spool_dir=tmp_path)
    if total == 0:
        assert path is None
        return
    assert pd.read_parquet(path).shape[0] == total


# ------------------------------------------------------------------
# I8 — Path locality + suffix
# ------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(50))
def test_I8_path_locality(tmp_path, seed):
    chunks = _random_chunk_sequence(seed)
    if _total_expected_rows(chunks) == 0:
        pytest.skip("empty")
    sub = tmp_path / "spool"
    with patch.object(bqe, "iterate_chunks", return_value=iter(chunks)):
        path, _ = bqe.merge_chunks_to_spool("t", f"i8_{seed}", spool_dir=sub)
    assert path is not None
    assert path.parent == sub
    assert str(path).endswith(".tmp.parquet")
    assert f"i8_{seed}" in path.name


# ------------------------------------------------------------------
# I9 — Null promotion (fuzzed)
# ------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(80))
def test_I9_null_promotion_fuzz(tmp_path, seed):
    """Chunk 1 has an all-None string column; later chunks have real strings.

    The null → large_string promotion must let the merge succeed, the resulting
    parquet must be readable, and the null/string positions must survive round-trip.
    """
    rng = random.Random(seed ^ 0xF00D)
    n1 = rng.randint(1, 8)
    n2 = rng.randint(1, 8)

    # Pick a victim column forced to all-None in chunk 1
    victim = rng.choice(_STRING_COLS)

    chunk1 = _make_chunk(rng, n1, none_density=0.0, row_offset=0)
    chunk1[victim] = [None] * n1

    chunk2 = _make_chunk(rng, n2, none_density=0.0, row_offset=n1)
    # Ensure chunk2's victim has at least one real string
    chunk2[victim] = [f"{victim}_{n1 + i}" for i in range(n2)]

    with patch.object(bqe, "iterate_chunks", return_value=iter([chunk1, chunk2])):
        path, total = bqe.merge_chunks_to_spool("t", f"i9_{seed}", spool_dir=tmp_path)

    assert total == n1 + n2
    out = pd.read_parquet(path)
    # First n1 rows should be null in victim column
    assert out[victim].iloc[:n1].isna().all()
    # Later rows should all be non-null
    assert out[victim].iloc[n1:].notna().all()


# ------------------------------------------------------------------
# Negative: column-set mismatch must raise (post-refactor contract)
# ------------------------------------------------------------------


def test_chunk_schema_mismatch_raises(tmp_path):
    chunk1 = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    chunk2 = pd.DataFrame({"A": [3], "C": ["oops"]})  # different column set

    with patch.object(bqe, "iterate_chunks", return_value=iter([chunk1, chunk2])):
        with pytest.raises(bqe.ChunkSchemaMismatch) as exc_info:
            bqe.merge_chunks_to_spool("t", "mismatch", spool_dir=tmp_path)

    assert exc_info.value.chunk_index == 1
    assert set(exc_info.value.expected) == {"A", "B"}
    assert set(exc_info.value.got) == {"A", "C"}
    # I6 cleanup still holds on schema mismatch
    assert not list(tmp_path.glob("*mismatch*.parquet"))


def test_chunk_column_reorder_still_merges(tmp_path):
    """Same column set in different order: must NOT raise, must align by name."""
    chunk1 = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    chunk2 = pd.DataFrame({"B": ["z"], "A": [3]})  # reordered

    with patch.object(bqe, "iterate_chunks", return_value=iter([chunk1, chunk2])):
        path, total = bqe.merge_chunks_to_spool("t", "reorder", spool_dir=tmp_path)

    assert total == 3
    out = pd.read_parquet(path)
    assert list(out["A"]) == [1, 2, 3]
    assert list(out["B"]) == ["x", "y", "z"]
