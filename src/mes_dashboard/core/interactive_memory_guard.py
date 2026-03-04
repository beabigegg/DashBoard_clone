# -*- coding: utf-8 -*-
"""Interactive memory guard — reusable DataFrame + RSS projection guard.

Extracted from reject_dataset_cache to allow cross-tool reuse.
Prevents expensive in-memory operations from pushing worker RSS over limit.

Two-fence approach:
  Fence 1: Reject if DataFrame alone exceeds max_input_mb
  Fence 2: Reject if (current RSS + DataFrame * working_set_factor) exceeds max_projected_rss_mb
"""

from __future__ import annotations

import gc
import logging
import os
from typing import Optional

import pandas as pd

logger = logging.getLogger("mes_dashboard.interactive_memory_guard")


# ============================================================
# RSS / DataFrame measurement helpers
# ============================================================

def process_rss_mb() -> Optional[float]:
    """Return current process RSS in MB via psutil, or None if unavailable."""
    try:
        import psutil  # local import: optional runtime dependency
    except Exception:
        return None
    try:
        return float(psutil.Process(os.getpid()).memory_info().rss) / (1024 * 1024)
    except Exception:
        return None


def df_memory_mb(df: pd.DataFrame) -> float:
    """Return deep memory usage of a DataFrame in MB."""
    if df is None or df.empty:
        return 0.0
    try:
        return float(df.memory_usage(deep=True).sum()) / (1024 * 1024)
    except Exception:
        return 0.0


# ============================================================
# Main guard
# ============================================================

def enforce_dataset_memory_guard(
    df: pd.DataFrame,
    *,
    operation: str,
    query_id: str = "",
    max_input_mb: float = 96.0,
    max_projected_rss_mb: float = 1100.0,
    working_set_factor: float = 1.8,
) -> None:
    """Raise MemoryError if DataFrame or projected RSS exceeds limits.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame about to be processed.
    operation : str
        Human-readable label for log/error messages (e.g. "視圖查詢").
    query_id : str
        Optional query identifier for log correlation.
    max_input_mb : float
        Reject if ``df_memory_mb(df) > max_input_mb``.
    max_projected_rss_mb : float
        Reject if ``current_rss + df_mb * working_set_factor > max_projected_rss_mb``.
    working_set_factor : float
        Multiplier estimating peak memory during processing.
    """
    if df is None or df.empty:
        return

    # Fence 1: DataFrame size
    mb = df_memory_mb(df)
    if mb > max_input_mb:
        logger.warning(
            "Reject %s due to dataset size guard (query_id=%s, df_mb=%.1f, limit_mb=%.0f)",
            operation, query_id, mb, max_input_mb,
        )
        raise MemoryError(
            f"{operation}資料量約 {mb:.1f} MB，超過 {max_input_mb:.0f} MB 上限，請縮小篩選條件後重試"
        )

    # Fence 2: RSS projection
    rss_mb = process_rss_mb()
    if rss_mb is None:
        return  # fail-open if psutil unavailable

    projected = rss_mb + (mb * working_set_factor)
    if projected > max_projected_rss_mb:
        logger.warning(
            "Reject %s due to projected RSS guard "
            "(query_id=%s, rss_mb=%.1f, df_mb=%.1f, factor=%.2f, projected_mb=%.1f, limit_mb=%.0f)",
            operation, query_id, rss_mb, mb, working_set_factor, projected, max_projected_rss_mb,
        )
        raise MemoryError(
            f"目前服務記憶體負載較高（RSS {rss_mb:.1f} MB），暫停{operation}計算以保護系統，"
            "請稍後再試或縮小篩選條件"
        )


def maybe_gc_collect(*, force: bool = True) -> None:
    """Optionally run gc.collect() after interactive computation."""
    if not force:
        return
    try:
        gc.collect()
    except Exception:
        pass
