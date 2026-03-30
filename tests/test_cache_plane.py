# -*- coding: utf-8 -*-
"""Tests for mes_dashboard.core.cache_plane module."""

import pytest

from mes_dashboard.core.cache_plane import (
    CachePlane,
    SNAPSHOT_REDIS_TTL_MULTIPLIER,
    SNAPSHOT_REDIS_TTL_FLOOR_SECONDS,
    snapshot_redis_ttl,
    HEAVY_QUERY_STATUS_PENDING,
    HEAVY_QUERY_STATUS_RUNNING,
    HEAVY_QUERY_STATUS_READY,
    HEAVY_QUERY_STATUS_FAILED,
    HEAVY_QUERY_STATUS_EXPIRED,
    CONTROL_PLANE_KEY_SEGMENT,
)


class TestCachePlaneEnum:
    def test_four_planes_defined(self):
        assert set(CachePlane) == {
            CachePlane.SNAPSHOT,
            CachePlane.HEAVY_QUERY,
            CachePlane.DERIVED_RESULT,
            CachePlane.CONTROL,
        }

    def test_plane_values(self):
        assert CachePlane.SNAPSHOT.value == "snapshot"
        assert CachePlane.HEAVY_QUERY.value == "heavy-query"
        assert CachePlane.DERIVED_RESULT.value == "derived-result"
        assert CachePlane.CONTROL.value == "control"

    def test_plane_is_str(self):
        """CachePlane inherits from str so it can be used as a dict key directly."""
        assert isinstance(CachePlane.SNAPSHOT, str)


class TestSnapshotRedisTtl:
    def test_normal_sync_interval(self):
        """TTL should be sync_interval * multiplier."""
        ttl = snapshot_redis_ttl(86_400)
        assert ttl == 86_400 * SNAPSHOT_REDIS_TTL_MULTIPLIER

    def test_small_sync_interval_uses_floor(self):
        """When multiplied TTL is below the floor, the floor is returned."""
        ttl = snapshot_redis_ttl(100)
        assert ttl == SNAPSHOT_REDIS_TTL_FLOOR_SECONDS

    def test_floor_boundary(self):
        """At the boundary, floor wins when multiplied result equals floor."""
        boundary = SNAPSHOT_REDIS_TTL_FLOOR_SECONDS // SNAPSHOT_REDIS_TTL_MULTIPLIER
        ttl = snapshot_redis_ttl(boundary)
        assert ttl == SNAPSHOT_REDIS_TTL_FLOOR_SECONDS

    def test_above_floor_boundary(self):
        boundary = SNAPSHOT_REDIS_TTL_FLOOR_SECONDS // SNAPSHOT_REDIS_TTL_MULTIPLIER
        ttl = snapshot_redis_ttl(boundary + 1)
        assert ttl == (boundary + 1) * SNAPSHOT_REDIS_TTL_MULTIPLIER

    def test_zero_interval_returns_floor(self):
        assert snapshot_redis_ttl(0) == SNAPSHOT_REDIS_TTL_FLOOR_SECONDS


class TestHeavyQueryStatusValues:
    def test_status_values_are_strings(self):
        statuses = [
            HEAVY_QUERY_STATUS_PENDING,
            HEAVY_QUERY_STATUS_RUNNING,
            HEAVY_QUERY_STATUS_READY,
            HEAVY_QUERY_STATUS_FAILED,
            HEAVY_QUERY_STATUS_EXPIRED,
        ]
        for s in statuses:
            assert isinstance(s, str)

    def test_status_values_unique(self):
        statuses = [
            HEAVY_QUERY_STATUS_PENDING,
            HEAVY_QUERY_STATUS_RUNNING,
            HEAVY_QUERY_STATUS_READY,
            HEAVY_QUERY_STATUS_FAILED,
            HEAVY_QUERY_STATUS_EXPIRED,
        ]
        assert len(set(statuses)) == 5


class TestControlPlaneKeySegment:
    def test_control_plane_key_segment_defined(self):
        assert CONTROL_PLANE_KEY_SEGMENT == "ctrl"
