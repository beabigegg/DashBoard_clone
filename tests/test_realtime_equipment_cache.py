# -*- coding: utf-8 -*-
"""Unit tests for realtime_equipment_cache module.

Tests aggregation, status classification, and cache query functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
import json
from datetime import datetime, timedelta
import pandas as pd


class TestClassifyStatus:
    """Test _classify_status function."""

    def test_classifies_prd_as_productive(self):
        """Test PRD status is classified as PRODUCTIVE."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('PRD')
        assert result == 'PRODUCTIVE'

    def test_classifies_sby_as_standby(self):
        """Test SBY status is classified as STANDBY."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('SBY')
        assert result == 'STANDBY'

    def test_classifies_udt_as_down(self):
        """Test UDT status is classified as DOWN."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('UDT')
        assert result == 'DOWN'

    def test_classifies_sdt_as_down(self):
        """Test SDT status is classified as DOWN."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('SDT')
        assert result == 'DOWN'

    def test_classifies_egt_as_engineering(self):
        """Test EGT status is classified as ENGINEERING."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('EGT')
        assert result == 'ENGINEERING'

    def test_classifies_nst_as_not_scheduled(self):
        """Test NST status is classified as NOT_SCHEDULED."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('NST')
        assert result == 'NOT_SCHEDULED'

    def test_classifies_scrap_as_inactive(self):
        """Test SCRAP status is classified as INACTIVE."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('SCRAP')
        assert result == 'INACTIVE'

    def test_classifies_unknown_as_other(self):
        """Test unknown status is classified as OTHER."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('UNKNOWN_STATUS')
        assert result == 'OTHER'

    def test_handles_none_status(self):
        """Test None status is classified as OTHER."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status(None)
        assert result == 'OTHER'

    def test_handles_empty_status(self):
        """Test empty string status is classified as OTHER."""
        from mes_dashboard.services.realtime_equipment_cache import _classify_status

        result = _classify_status('')
        assert result == 'OTHER'


class TestAggregateByResourceid:
    """Test _aggregate_by_resourceid function."""

    def test_aggregates_single_record(self):
        """Test aggregation with single record per resource."""
        from mes_dashboard.services.realtime_equipment_cache import _aggregate_by_resourceid

        records = [
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'RUNCARDLOTID': 'LOT001',
                'JOBORDER': 'JO001',
                'JOBSTATUS': 'RUN',
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': 100,
                'LOTTRACKINTIME': '2024-01-15T10:00:00',
            }
        ]

        result = _aggregate_by_resourceid(records)

        assert len(result) == 1
        assert result[0]['RESOURCEID'] == 'R001'
        assert result[0]['LOT_COUNT'] == 1
        assert result[0]['TOTAL_TRACKIN_QTY'] == 100
        assert result[0]['STATUS_CATEGORY'] == 'PRODUCTIVE'

    def test_aggregates_multiple_lots(self):
        """Test aggregation with multiple LOTs per resource (e.g., oven)."""
        from mes_dashboard.services.realtime_equipment_cache import _aggregate_by_resourceid

        records = [
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'RUNCARDLOTID': 'LOT001',
                'JOBORDER': 'JO001',
                'JOBSTATUS': 'RUN',
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': 100,
                'LOTTRACKINTIME': '2024-01-15T10:00:00',
            },
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'RUNCARDLOTID': 'LOT002',
                'JOBORDER': 'JO002',
                'JOBSTATUS': 'RUN',
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': 150,
                'LOTTRACKINTIME': '2024-01-15T11:00:00',
            },
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'RUNCARDLOTID': 'LOT003',
                'JOBORDER': 'JO003',
                'JOBSTATUS': 'RUN',
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': 50,
                'LOTTRACKINTIME': '2024-01-15T09:00:00',
            },
        ]

        result = _aggregate_by_resourceid(records)

        assert len(result) == 1
        assert result[0]['RESOURCEID'] == 'R001'
        assert result[0]['LOT_COUNT'] == 3
        assert result[0]['TOTAL_TRACKIN_QTY'] == 300  # 100 + 150 + 50
        assert result[0]['LATEST_TRACKIN_TIME'] == '2024-01-15T11:00:00'

    def test_aggregates_multiple_resources(self):
        """Test aggregation with multiple different resources."""
        from mes_dashboard.services.realtime_equipment_cache import _aggregate_by_resourceid

        records = [
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'RUNCARDLOTID': 'LOT001',
                'JOBORDER': 'JO001',
                'JOBSTATUS': 'RUN',
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': 100,
                'LOTTRACKINTIME': '2024-01-15T10:00:00',
            },
            {
                'RESOURCEID': 'R002',
                'EQUIPMENTID': 'E002',
                'OBJECTCATEGORY': 'WAFERSORT',
                'EQUIPMENTASSETSSTATUS': 'SBY',
                'EQUIPMENTASSETSSTATUSREASON': 'Waiting',
                'RUNCARDLOTID': None,
                'JOBORDER': None,
                'JOBSTATUS': None,
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': None,
                'LOTTRACKINTIME': None,
            },
        ]

        result = _aggregate_by_resourceid(records)

        assert len(result) == 2
        r1 = next(r for r in result if r['RESOURCEID'] == 'R001')
        r2 = next(r for r in result if r['RESOURCEID'] == 'R002')

        assert r1['LOT_COUNT'] == 1
        assert r1['STATUS_CATEGORY'] == 'PRODUCTIVE'
        assert r2['LOT_COUNT'] == 0
        assert r2['STATUS_CATEGORY'] == 'STANDBY'

    def test_handles_empty_records(self):
        """Test handles empty record list."""
        from mes_dashboard.services.realtime_equipment_cache import _aggregate_by_resourceid

        result = _aggregate_by_resourceid([])
        assert result == []

    def test_handles_null_quantities(self):
        """Test handles null quantities gracefully."""
        from mes_dashboard.services.realtime_equipment_cache import _aggregate_by_resourceid

        records = [
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'SBY',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'JOBORDER': None,
                'JOBSTATUS': None,
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': None,
                'LOTTRACKINTIME': None,
            }
        ]

        result = _aggregate_by_resourceid(records)

        assert len(result) == 1
        assert result[0]['TOTAL_TRACKIN_QTY'] == 0
        assert result[0]['LATEST_TRACKIN_TIME'] is None

    def test_skips_records_without_resourceid(self):
        """Test skips records without RESOURCEID."""
        from mes_dashboard.services.realtime_equipment_cache import _aggregate_by_resourceid

        records = [
            {
                'RESOURCEID': None,
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'JOBORDER': None,
                'JOBSTATUS': None,
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': 100,
                'LOTTRACKINTIME': '2024-01-15T10:00:00',
            },
            {
                'RESOURCEID': 'R001',
                'EQUIPMENTID': 'E001',
                'OBJECTCATEGORY': 'ASSEMBLY',
                'EQUIPMENTASSETSSTATUS': 'PRD',
                'EQUIPMENTASSETSSTATUSREASON': None,
                'JOBORDER': None,
                'JOBSTATUS': None,
                'SYMPTOMCODE': None,
                'CAUSECODE': None,
                'REPAIRCODE': None,
                'LOTTRACKINQTY_PCS': 50,
                'LOTTRACKINTIME': '2024-01-15T10:00:00',
            },
        ]

        result = _aggregate_by_resourceid(records)

        assert len(result) == 1
        assert result[0]['RESOURCEID'] == 'R001'


class TestGetEquipmentStatusById:
    """Test get_equipment_status_by_id function."""

    @pytest.fixture(autouse=True)
    def reset_modules(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        import mes_dashboard.services.realtime_equipment_cache as eq
        rc._REDIS_CLIENT = None
        eq._equipment_status_cache.invalidate("equipment_status_all")
        eq._invalidate_equipment_status_lookup()
        yield
        rc._REDIS_CLIENT = None
        eq._equipment_status_cache.invalidate("equipment_status_all")
        eq._invalidate_equipment_status_lookup()

    def test_returns_none_when_redis_unavailable(self):
        """Test returns None when Redis client unavailable."""
        from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_by_id

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=None):
            result = get_equipment_status_by_id('R001')
            assert result is None

    def test_returns_none_when_id_not_found(self):
        """Test returns None when resource ID not in index."""
        from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_by_id

        mock_client = MagicMock()
        mock_client.hget.return_value = None

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=mock_client):
            with patch('mes_dashboard.services.realtime_equipment_cache.get_key_prefix', return_value='mes_wip'):
                result = get_equipment_status_by_id('R999')
                assert result is None

    def test_returns_matching_record(self):
        """Test returns matching record from cache."""
        from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_by_id

        test_data = [
            {'RESOURCEID': 'R001', 'STATUS_CATEGORY': 'PRODUCTIVE'},
            {'RESOURCEID': 'R002', 'STATUS_CATEGORY': 'STANDBY'},
        ]

        mock_client = MagicMock()
        mock_client.hget.return_value = '1'  # Index 1 -> R002
        mock_client.get.return_value = json.dumps(test_data)

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=mock_client):
            with patch('mes_dashboard.services.realtime_equipment_cache.get_key_prefix', return_value='mes_wip'):
                result = get_equipment_status_by_id('R002')

                assert result is not None
                assert result['RESOURCEID'] == 'R002'
                assert result['STATUS_CATEGORY'] == 'STANDBY'


class TestGetEquipmentStatusByIds:
    """Test get_equipment_status_by_ids function."""

    @pytest.fixture(autouse=True)
    def reset_modules(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        import mes_dashboard.services.realtime_equipment_cache as eq
        rc._REDIS_CLIENT = None
        eq._equipment_status_cache.invalidate("equipment_status_all")
        eq._invalidate_equipment_status_lookup()
        yield
        rc._REDIS_CLIENT = None
        eq._equipment_status_cache.invalidate("equipment_status_all")
        eq._invalidate_equipment_status_lookup()

    def test_returns_empty_for_empty_input(self):
        """Test returns empty list for empty input."""
        from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_by_ids

        result = get_equipment_status_by_ids([])
        assert result == []

    def test_returns_empty_when_redis_unavailable(self):
        """Test returns empty list when Redis unavailable."""
        from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_by_ids

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=None):
            result = get_equipment_status_by_ids(['R001', 'R002'])
            assert result == []

    def test_returns_matching_records(self):
        """Test returns all matching records."""
        from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_by_ids

        test_data = [
            {'RESOURCEID': 'R001', 'STATUS_CATEGORY': 'PRODUCTIVE'},
            {'RESOURCEID': 'R002', 'STATUS_CATEGORY': 'STANDBY'},
            {'RESOURCEID': 'R003', 'STATUS_CATEGORY': 'DOWN'},
        ]

        mock_client = MagicMock()
        mock_client.hmget.return_value = ['0', '2', None]  # R001 at idx 0, R003 at idx 2, R999 not found
        mock_client.get.return_value = json.dumps(test_data)

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=mock_client):
            with patch('mes_dashboard.services.realtime_equipment_cache.get_key_prefix', return_value='mes_wip'):
                result = get_equipment_status_by_ids(['R001', 'R003', 'R999'])

                assert len(result) == 2
                ids = [r['RESOURCEID'] for r in result]
                assert 'R001' in ids
                assert 'R003' in ids
                assert 'R999' not in ids


class TestGetAllEquipmentStatus:
    """Test get_all_equipment_status function."""

    @pytest.fixture(autouse=True)
    def reset_modules(self):
        """Reset module state before each test."""
        import mes_dashboard.core.redis_client as rc
        import mes_dashboard.services.realtime_equipment_cache as eq
        rc._REDIS_CLIENT = None
        eq._equipment_status_cache.invalidate("equipment_status_all")
        eq._invalidate_equipment_status_lookup()
        yield
        rc._REDIS_CLIENT = None
        eq._equipment_status_cache.invalidate("equipment_status_all")
        eq._invalidate_equipment_status_lookup()

    def test_returns_empty_when_redis_unavailable(self):
        """Test returns empty list when Redis unavailable."""
        from mes_dashboard.services.realtime_equipment_cache import get_all_equipment_status

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=None):
            result = get_all_equipment_status()
            assert result == []

    def test_returns_empty_when_no_data(self):
        """Test returns empty list when no data in cache."""
        from mes_dashboard.services.realtime_equipment_cache import get_all_equipment_status

        mock_client = MagicMock()
        mock_client.get.return_value = None

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=mock_client):
            with patch('mes_dashboard.services.realtime_equipment_cache.get_key_prefix', return_value='mes_wip'):
                result = get_all_equipment_status()
                assert result == []

    def test_returns_all_cached_data(self):
        """Test returns all cached equipment status."""
        from mes_dashboard.services.realtime_equipment_cache import get_all_equipment_status

        test_data = [
            {'RESOURCEID': 'R001', 'STATUS_CATEGORY': 'PRODUCTIVE'},
            {'RESOURCEID': 'R002', 'STATUS_CATEGORY': 'STANDBY'},
        ]

        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps(test_data)

        with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=mock_client):
            with patch('mes_dashboard.services.realtime_equipment_cache.get_key_prefix', return_value='mes_wip'):
                result = get_all_equipment_status()

                assert len(result) == 2
                assert result[0]['RESOURCEID'] == 'R001'
                assert result[1]['RESOURCEID'] == 'R002'


class TestGetEquipmentStatusCacheStatus:
    """Test get_equipment_status_cache_status function."""

    @pytest.fixture
    def app(self):
        """Create application for testing."""
        from mes_dashboard.app import create_app
        import mes_dashboard.core.database as db
        db._ENGINE = None
        app = create_app('testing')
        app.config['TESTING'] = True
        return app

    def test_returns_disabled_when_cache_disabled(self, app):
        """Test returns disabled status when cache is disabled."""
        app.config['REALTIME_EQUIPMENT_CACHE_ENABLED'] = False

        with app.app_context():
            from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_cache_status
            result = get_equipment_status_cache_status()

            assert result['enabled'] is False
            assert result['loaded'] is False

    def test_returns_loaded_status_when_data_exists(self, app):
        """Test returns loaded status when cache has data."""
        app.config['REALTIME_EQUIPMENT_CACHE_ENABLED'] = True

        mock_client = MagicMock()
        mock_client.get.side_effect = lambda key: {
            'mes_wip:equipment_status:meta:updated': '2024-01-15T10:30:00',
            'mes_wip:equipment_status:meta:count': '1000',
        }.get(key)

        with app.app_context():
            with patch('mes_dashboard.services.realtime_equipment_cache.get_redis_client', return_value=mock_client):
                with patch('mes_dashboard.services.realtime_equipment_cache.get_key_prefix', return_value='mes_wip'):
                    from mes_dashboard.services.realtime_equipment_cache import get_equipment_status_cache_status
                    result = get_equipment_status_cache_status()

                    assert result['enabled'] is True
                    assert result['loaded'] is True
                    assert result['count'] == 1000


class TestEquipmentProcessLevelCache:
    """Test bounded process-level cache behavior for equipment status."""

    def test_lru_eviction_prefers_recent_keys(self):
        import mes_dashboard.services.realtime_equipment_cache as eq

        cache = eq._ProcessLevelCache(ttl_seconds=60, max_size=2)
        cache.set("a", [{"RESOURCEID": "R001"}])
        cache.set("b", [{"RESOURCEID": "R002"}])
        assert cache.get("a") is not None  # refresh recency
        cache.set("c", [{"RESOURCEID": "R003"}])  # should evict "b"

        assert cache.get("b") is None
        assert cache.get("a") is not None
        assert cache.get("c") is not None

    def test_global_equipment_cache_uses_bounded_config(self):
        import mes_dashboard.services.realtime_equipment_cache as eq

        assert eq.EQUIPMENT_PROCESS_CACHE_MAX_SIZE >= 1
        assert eq._equipment_status_cache.max_size == eq.EQUIPMENT_PROCESS_CACHE_MAX_SIZE


class TestEquipmentRefreshDedup:
    """Test refresh de-dup behavior and sync worker startup timing."""

    def test_refresh_skips_when_recently_updated(self):
        """Should skip Oracle query when cache is fresh and force=False."""
        import mes_dashboard.services.realtime_equipment_cache as eq

        recent_updated = (datetime.now() - timedelta(seconds=10)).isoformat()
        mock_client = MagicMock()
        mock_client.get.return_value = recent_updated

        with patch.object(eq, "_SYNC_INTERVAL", 300):
            with patch.object(eq, "try_acquire_lock", return_value=True):
                with patch.object(eq, "release_lock") as mock_release_lock:
                    with patch.object(eq, "get_redis_client", return_value=mock_client):
                        with patch.object(eq, "get_key_prefix", return_value="mes_wip"):
                            with patch.object(eq, "_load_equipment_status_from_oracle") as mock_oracle:
                                with patch.object(eq, "_save_to_redis", return_value=True) as mock_save:
                                    result = eq.refresh_equipment_status_cache(force=False)

        assert result is False
        mock_oracle.assert_not_called()
        mock_save.assert_not_called()
        mock_client.get.assert_called_once_with("mes_wip:equipment_status:meta:updated")
        mock_release_lock.assert_called_once_with("equipment_status_cache_update")

    def test_refresh_proceeds_when_stale(self):
        """Should proceed with Oracle query when cache is stale."""
        import mes_dashboard.services.realtime_equipment_cache as eq

        stale_updated = (datetime.now() - timedelta(seconds=200)).isoformat()
        mock_client = MagicMock()
        mock_client.get.return_value = stale_updated

        with patch.object(eq, "_SYNC_INTERVAL", 300):
            with patch.object(eq, "try_acquire_lock", return_value=True):
                with patch.object(eq, "release_lock"):
                    with patch.object(eq, "get_redis_client", return_value=mock_client):
                        with patch.object(eq, "get_key_prefix", return_value="mes_wip"):
                            with patch.object(eq, "_load_equipment_status_from_oracle", return_value=[{"RESOURCEID": "R001"}]) as mock_oracle:
                                with patch.object(eq, "_aggregate_by_resourceid", return_value=[{"RESOURCEID": "R001"}]):
                                    with patch.object(eq, "_save_to_redis", return_value=True) as mock_save:
                                        result = eq.refresh_equipment_status_cache(force=False)

        assert result is True
        mock_oracle.assert_called_once()
        mock_save.assert_called_once()

    def test_refresh_proceeds_when_force(self):
        """Should bypass freshness gate when force=True."""
        import mes_dashboard.services.realtime_equipment_cache as eq

        with patch.object(eq, "_SYNC_INTERVAL", 300):
            with patch.object(eq, "try_acquire_lock", return_value=True):
                with patch.object(eq, "release_lock"):
                    with patch.object(eq, "get_redis_client") as mock_get_redis_client:
                        with patch.object(eq, "_load_equipment_status_from_oracle", return_value=[{"RESOURCEID": "R001"}]) as mock_oracle:
                            with patch.object(eq, "_aggregate_by_resourceid", return_value=[{"RESOURCEID": "R001"}]):
                                with patch.object(eq, "_save_to_redis", return_value=True) as mock_save:
                                    result = eq.refresh_equipment_status_cache(force=True)

        assert result is True
        mock_oracle.assert_called_once()
        mock_save.assert_called_once()
        mock_get_redis_client.assert_not_called()

    def test_sync_worker_waits_before_first_refresh(self):
        """Sync worker should not refresh immediately on startup."""
        import mes_dashboard.services.realtime_equipment_cache as eq

        class StopImmediatelyEvent:
            def __init__(self):
                self.timeouts = []

            def wait(self, timeout=None):
                self.timeouts.append(timeout)
                return True

        fake_stop_event = StopImmediatelyEvent()

        with patch.object(eq, "_STOP_EVENT", fake_stop_event):
            with patch.object(eq, "refresh_equipment_status_cache") as mock_refresh:
                eq._sync_worker(interval=300)

        mock_refresh.assert_not_called()
        assert fake_stop_event.timeouts == [300]


class TestSharedQueryFragments:
    """Test shared SQL fragment governance for equipment cache."""

    def test_equipment_load_uses_shared_sql_fragment(self):
        import mes_dashboard.services.realtime_equipment_cache as eq
        from mes_dashboard.services.sql_fragments import EQUIPMENT_STATUS_SELECT_SQL

        mock_df = pd.DataFrame([{"RESOURCEID": "R001", "EQUIPMENTID": "EQ-01"}])
        with patch.object(eq, "read_sql_df", return_value=mock_df) as mock_read:
            eq._load_equipment_status_from_oracle()

        sql = mock_read.call_args[0][0]
        assert sql.strip() == EQUIPMENT_STATUS_SELECT_SQL.strip()
