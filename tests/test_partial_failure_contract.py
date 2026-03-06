# -*- coding: utf-8 -*-
"""Unit tests for reusable partial-failure metadata helpers."""

from mes_dashboard.core.partial_failure_contract import (
    build_partial_failure_meta,
    merge_partial_failure_meta,
    parse_partial_failure_meta,
    serialize_partial_failure_meta,
)


def test_build_partial_failure_meta_normalizes_count_and_ranges():
    meta = build_partial_failure_meta(
        failed_count="2",
        failed_ranges=[
            {"start": "2025-01-01", "end": "2025-01-10"},
            {"start": "", "end": "2025-01-20"},
        ],
    )

    assert meta == {
        "has_partial_failure": True,
        "failed_chunk_count": 2,
        "failed_ranges": [{"start": "2025-01-01", "end": "2025-01-10"}],
    }


def test_parse_partial_failure_meta_supports_redis_hash_shape():
    parsed = parse_partial_failure_meta(
        {
            "has_partial_failure": "True",
            "failed_chunk_count": "3",
            "failed_ranges": '[{"start":"A","end":"B"}]',
        }
    )

    assert parsed["has_partial_failure"] is True
    assert parsed["failed_chunk_count"] == 3
    assert parsed["failed_ranges"] == [{"start": "A", "end": "B"}]


def test_serialize_partial_failure_meta_roundtrip():
    raw = serialize_partial_failure_meta(
        {
            "has_partial_failure": True,
            "failed_chunk_count": 1,
            "failed_ranges": [{"start": "S", "end": "E"}],
        }
    )
    parsed = parse_partial_failure_meta(raw)

    assert parsed == {
        "has_partial_failure": True,
        "failed_chunk_count": 1,
        "failed_ranges": [{"start": "S", "end": "E"}],
    }


def test_merge_partial_failure_meta_accumulates_ranges_and_counts():
    merged = merge_partial_failure_meta(
        [
            {"has_partial_failure": True, "failed_chunk_count": 1, "failed_ranges": [{"start": "1", "end": "2"}]},
            {"has_partial_failure": "True", "failed_chunk_count": "2", "failed_ranges": [{"start": "3", "end": "4"}]},
        ]
    )

    assert merged["has_partial_failure"] is True
    assert merged["failed_chunk_count"] == 3
    assert merged["failed_ranges"] == [{"start": "1", "end": "2"}, {"start": "3", "end": "4"}]
