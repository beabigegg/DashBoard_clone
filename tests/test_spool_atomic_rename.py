# -*- coding: utf-8 -*-
"""Tests: atomic rename semantics in query_spool_store._move_into_place().

Verifies:
  - _move_into_place uses src.replace(dest) (POSIX atomic rename)
  - Falls back to shutil.move when src.replace raises OSError
  - Reader never observes a partial (torn) write

These tests are unit-level (no DB, no Redis) and run without --run-integration.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Import target
# ---------------------------------------------------------------------------

from mes_dashboard.core.query_spool_store import _move_into_place


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_large_parquet(path: Path, rows: int = 50_000) -> None:
    """Write a reasonably-sized parquet file to *path*."""
    df = pd.DataFrame({
        "id": range(rows),
        "value": [f"data_{i}" for i in range(rows)],
        "qty": [float(i) * 1.1 for i in range(rows)],
    })
    df.to_parquet(path, engine="pyarrow", index=False)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSpoolAtomicRename:
    """Verify _move_into_place atomic-rename contract."""

    # ------------------------------------------------------------------ #
    # 6.14.1 — Reader never sees a partial file during atomic rename     #
    # ------------------------------------------------------------------ #

    def test_reader_never_sees_partial_write(self, tmp_path):
        """Reader either misses (None) or sees the complete file; never partial."""
        tmp_src = tmp_path / "result.tmp"
        dest = tmp_path / "result.parquet"

        # Write large enough data to trigger real I/O time.
        _write_large_parquet(tmp_src, rows=100_000)
        expected_size = tmp_src.stat().st_size
        assert expected_size > 0

        observations: list[str] = []
        stop_event = threading.Event()

        def reader_thread():
            """Poll the canonical path until writer signals done."""
            while not stop_event.is_set():
                if dest.exists():
                    size = dest.stat().st_size
                    if size == 0:
                        observations.append("empty")
                    elif size < expected_size:
                        observations.append(f"partial:{size}")
                    else:
                        observations.append(f"complete:{size}")
                else:
                    observations.append("miss")
                time.sleep(0.0001)

        t = threading.Thread(target=reader_thread, daemon=True)
        t.start()

        # Perform atomic rename.
        _move_into_place(tmp_src, dest)

        stop_event.set()
        t.join(timeout=2)

        # Verify: no "partial" or "empty" observations.
        bad = [o for o in observations if o.startswith("partial:") or o == "empty"]
        assert not bad, (
            f"Reader observed partial/empty state {len(bad)} time(s): {bad[:5]}"
        )
        # At least one observation must exist.
        assert observations, "Reader thread produced no observations"
        # All non-miss observations must be complete.
        non_miss = [o for o in observations if not o.startswith("miss")]
        for obs in non_miss:
            assert obs.startswith("complete:"), f"Unexpected observation: {obs}"

    # ------------------------------------------------------------------ #
    # 6.14.2 — Uses src.replace (POSIX atomic); shutil.move NOT called   #
    # ------------------------------------------------------------------ #

    def test_move_into_place_is_atomic_on_posix(self, tmp_path):
        """When src.replace succeeds, shutil.move must NOT be called."""
        tmp_src = tmp_path / "data.tmp"
        dest = tmp_path / "data.parquet"
        tmp_src.write_bytes(b"fake parquet content")

        # Patch shutil.move so we can detect if it is called.
        with patch("mes_dashboard.core.query_spool_store.shutil.move") as mock_shutil_move:
            _move_into_place(tmp_src, dest)
            mock_shutil_move.assert_not_called()

        assert dest.exists(), "dest must exist after successful rename"
        assert not tmp_src.exists(), "src must be gone after rename"

    # ------------------------------------------------------------------ #
    # 6.14.3 — Falls back to shutil.move on OSError from src.replace    #
    # ------------------------------------------------------------------ #

    def test_move_into_place_falls_back_on_oserror(self, tmp_path):
        """When src.replace raises OSError, shutil.move IS called as fallback."""
        tmp_src = tmp_path / "data.tmp"
        dest = tmp_path / "data.parquet"
        tmp_src.write_bytes(b"fake parquet content")

        original_replace = Path.replace

        def _failing_replace(self, target):
            if str(self) == str(tmp_src):
                raise OSError("simulated cross-device rename failure")
            return original_replace(self, target)

        with patch.object(Path, "replace", _failing_replace), \
             patch("mes_dashboard.core.query_spool_store.shutil.move") as mock_shutil_move:
            _move_into_place(tmp_src, dest)
            mock_shutil_move.assert_called_once_with(str(tmp_src), str(dest))

    # ------------------------------------------------------------------ #
    # 6.14.4 — Function signature accepts Path and str interchangeably   #
    # ------------------------------------------------------------------ #

    def test_move_into_place_accepts_str_paths(self, tmp_path):
        """_move_into_place must handle str arguments (not just Path objects)."""
        tmp_src = tmp_path / "str_src.tmp"
        dest = tmp_path / "str_dest.parquet"
        tmp_src.write_bytes(b"content")

        # Pass as strings, not Path objects.
        _move_into_place(str(tmp_src), str(dest))

        assert dest.exists()
        assert not tmp_src.exists()

    # ------------------------------------------------------------------ #
    # 6.14.5 — Dest is overwritten if it already exists                  #
    # ------------------------------------------------------------------ #

    def test_move_into_place_overwrites_existing_dest(self, tmp_path):
        """Atomic rename must overwrite an existing dest file (POSIX guarantee)."""
        tmp_src = tmp_path / "new.tmp"
        dest = tmp_path / "existing.parquet"

        dest.write_bytes(b"old content")
        tmp_src.write_bytes(b"new content")

        _move_into_place(tmp_src, dest)

        assert dest.exists()
        assert dest.read_bytes() == b"new content", "dest must contain the new content"
        assert not tmp_src.exists()
