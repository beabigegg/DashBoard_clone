# -*- coding: utf-8 -*-
"""Regression test: hold-history on-hold count must NOT scale with date-range length.

Root cause being pinned
-----------------------
When the queried date range exceeds the time-chunk grain (``grain_days=31`` in
``batch_query_engine.decompose_by_time_range``), ``hold_dataset_cache.execute_primary_query``
splits the range into N chunks and runs ``sql/hold_history/base_facts.sql`` once per
chunk, then concatenates the results into one Parquet spool via
``merge_chunks_to_spool`` (no dedup).

``base_facts.sql`` carries an ``OR h.RELEASETXNDATE IS NULL`` escape in BOTH AND-groups
of its WHERE clause (``base_facts.sql:63-72``).  That escape makes every currently-open
hold (``RELEASETXNDATE IS NULL``) pass the WHERE *regardless of the chunk's date window*,
so every chunk re-fetches the full set of open holds.  Concatenating N non-disjoint
chunk results writes each open-hold row N times → the ``on_hold`` view
(``hold_history_sql_runtime._build_record_type_clause`` → ``"RELEASETXNDATE" IS NULL``,
no date bound) counts the duplicates → the on-hold number balloons ~N×.

  range <= 31 days  -> 1 chunk  -> correct
  range 32-62 days  -> 2 chunks -> on-hold ~2x
  range 63-93 days  -> 3 chunks -> on-hold ~3x

These tests drive the REAL ``execute_primary_query`` (the function the fix will change),
substituting only Oracle (``read_sql_df`` emulates ``base_facts.sql`` semantics) and Redis
(in-memory mock — same pattern as ``tests/test_batch_query_engine.py``).  They assert that
the number of on-hold rows in the merged spool equals the true distinct open-hold count and
is invariant to the range length.  EXPECTED TO FAIL until the ③-b fix (single whole-range
chunk for hold) lands.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd

import mes_dashboard.core.redis_df_store as rds
import mes_dashboard.services.batch_query_engine as bqe
from mes_dashboard.services import hold_dataset_cache as cache_svc


# --- Synthetic source dataset (rows == base_facts.sql output) --------------------

# 2 open holds (RELEASETXNDATE is None), both held inside January 2025.
# 2 released holds, each released within a single 31-day chunk window.
_D = "%Y-%m-%d"


def _dt(s: str) -> datetime:
    return datetime.strptime(s, _D)


# CONTAINERID, HOLDTXNDATE, RELEASETXNDATE (None == still on hold)
_SOURCE = [
    {"CONTAINERID": "OPEN_1", "HOLDTXNDATE": _dt("2025-01-10"), "RELEASETXNDATE": None},
    {"CONTAINERID": "OPEN_2", "HOLDTXNDATE": _dt("2025-01-20"), "RELEASETXNDATE": None},
    {"CONTAINERID": "REL_1", "HOLDTXNDATE": _dt("2025-01-05"), "RELEASETXNDATE": _dt("2025-01-08")},
    {"CONTAINERID": "REL_2", "HOLDTXNDATE": _dt("2025-02-10"), "RELEASETXNDATE": _dt("2025-02-12")},
]

_NUM_OPEN = sum(1 for r in _SOURCE if r["RELEASETXNDATE"] is None)  # == 2

_COLS = [
    "CONTAINERID", "LOT_ID", "HOLDTXNDATE", "RELEASETXNDATE", "hold_day", "release_day",
    "HOLD_TYPE", "HOLDREASONNAME", "QTY", "HOLD_HOURS",
]


def _rows_to_df(rows: list[dict]) -> pd.DataFrame:
    """Build a base_facts-shaped DataFrame with stable dtypes (so chunk schemas match)."""
    records = []
    for r in rows:
        hold = r["HOLDTXNDATE"]
        rel = r["RELEASETXNDATE"]
        records.append({
            "CONTAINERID": r["CONTAINERID"],
            "LOT_ID": r["CONTAINERID"],
            "HOLDTXNDATE": hold,
            "RELEASETXNDATE": rel,
            "hold_day": hold,
            "release_day": rel,
            "HOLD_TYPE": "quality",
            "HOLDREASONNAME": "TEST_REASON",
            "QTY": 100,
            "HOLD_HOURS": 24.0,
        })
    df = pd.DataFrame(records, columns=_COLS)
    for col in ("HOLDTXNDATE", "RELEASETXNDATE", "hold_day", "release_day"):
        df[col] = pd.to_datetime(df[col])
    if not df.empty:
        df["QTY"] = df["QTY"].astype("int64")
        df["HOLD_HOURS"] = df["HOLD_HOURS"].astype("float64")
    return df


def _base_facts_emulator(sql, params, caller=None):
    """Faithfully emulate base_facts.sql's WHERE for one chunk window.

    Mirrors base_facts.sql:63-72 — the ``OR RELEASETXNDATE IS NULL`` escape means every
    open hold qualifies for EVERY chunk window.
    """
    start = _dt(params["start_date"]) - timedelta(days=1)  # base_facts uses start-1
    end = _dt(params["end_date"])
    selected = []
    for r in _SOURCE:
        hold = r["HOLDTXNDATE"]
        rel = r["RELEASETXNDATE"]
        g1 = (hold >= start) or (rel is not None and rel >= start) or (rel is None)
        g2 = (hold <= end) or (rel is not None and rel <= end) or (rel is None)
        if g1 and g2:
            selected.append(r)
    return _rows_to_df(selected)


def _make_mock_redis():
    """In-memory Redis double covering chunk store/load + progress hash."""
    stored: dict = {}
    hashes: dict = {}
    client = MagicMock()
    client.setex.side_effect = lambda k, t, v: stored.update({k: v})
    client.get.side_effect = lambda k: stored.get(k)
    client.exists.side_effect = lambda k: 1 if k in stored else 0
    client.hset.side_effect = lambda k, mapping=None: hashes.setdefault(k, {}).update(mapping or {})
    client.hgetall.side_effect = lambda k: hashes.get(k, {})
    client.expire.return_value = None
    client.delete.side_effect = lambda *ks: [stored.pop(k, None) for k in ks] and 0
    return client


def _run_pipeline(monkeypatch, tmp_path, start_date: str, end_date: str) -> pd.DataFrame:
    """Drive the real execute_primary_query and return the merged spool DataFrame."""
    captured: dict = {}

    def _fake_register(ns, qid, path, row_count, **kw):
        captured["path"] = path
        return path

    monkeypatch.setattr(cache_svc, "QUERY_SPOOL_DIR", str(tmp_path))
    monkeypatch.setattr(cache_svc, "_HOLD_ENGINE_PARALLEL", 1)
    monkeypatch.setattr(cache_svc, "_has_cached_df", lambda _qid: False)
    monkeypatch.setattr(cache_svc, "read_sql_df", _base_facts_emulator)
    monkeypatch.setattr(cache_svc, "_load_sql", lambda name: "SELECT 1 FROM dual")
    monkeypatch.setattr(cache_svc, "register_spool_file", _fake_register)
    monkeypatch.setattr(cache_svc, "_store_query_dates", lambda *a, **kw: None)
    monkeypatch.setattr(cache_svc, "apply_view", lambda **kw: {
        "trend": {"days": []}, "reason_pareto": {"items": []},
        "duration": {"items": []},
        "list": {"items": [], "pagination": {"page": 1, "perPage": 20, "total": 0, "totalPages": 1}},
        "_meta": {},
    })

    mock_client = _make_mock_redis()
    with patch.object(rds, "REDIS_ENABLED", True), \
            patch.object(rds, "get_redis_client", return_value=mock_client), \
            patch.object(bqe, "get_redis_client", return_value=mock_client):
        cache_svc.execute_primary_query(start_date=start_date, end_date=end_date)

    assert "path" in captured, "spool was never merged/registered"
    return pd.read_parquet(captured["path"], engine="pyarrow")


def _on_hold_rows(df: pd.DataFrame) -> int:
    return int(df["RELEASETXNDATE"].isna().sum())


class TestHoldOnHoldNotDuplicatedAcrossChunks:
    """On-hold (RELEASETXNDATE IS NULL) rows must not be duplicated per time-chunk."""

    def test_open_holds_not_multiplied_by_chunk_count(self, monkeypatch, tmp_path):
        """90-day range (3 chunks): on-hold rows must equal the true distinct open-hold count."""
        # 2025-01-01 .. 2025-03-31 → decompose_by_time_range yields 3 chunks.
        merged = _run_pipeline(monkeypatch, tmp_path, "2025-01-01", "2025-03-31")
        assert _on_hold_rows(merged) == _NUM_OPEN, (
            f"expected {_NUM_OPEN} on-hold rows, got {_on_hold_rows(merged)} "
            f"(open holds duplicated once per time-chunk)"
        )

    def test_on_hold_count_invariant_to_range_length(self, monkeypatch, tmp_path):
        """User-reported symptom: 32-day vs 90-day must report the SAME on-hold count."""
        merged_32 = _run_pipeline(monkeypatch, tmp_path, "2025-01-01", "2025-02-02")   # 2 chunks
        merged_90 = _run_pipeline(monkeypatch, tmp_path, "2025-01-01", "2025-03-31")   # 3 chunks
        assert _on_hold_rows(merged_32) == _on_hold_rows(merged_90), (
            f"on-hold count scaled with range length: "
            f"32-day={_on_hold_rows(merged_32)} vs 90-day={_on_hold_rows(merged_90)}"
        )

    def test_released_holds_are_not_inflated(self, monkeypatch, tmp_path):
        """Sanity: a short released hold (single-chunk window) appears exactly once."""
        merged = _run_pipeline(monkeypatch, tmp_path, "2025-01-01", "2025-03-31")
        rel_1 = merged[merged["CONTAINERID"] == "REL_1"]
        assert len(rel_1) == 1, (
            f"REL_1 (released 2025-01-08, single chunk) appeared {len(rel_1)}x — "
            f"duplication is supposed to hit only open/cross-boundary holds"
        )
