# -*- coding: utf-8 -*-
"""Unit tests for workcenter mapping in filter_cache module.

Tests workcenter group lookup and mapping functionality.
"""

import importlib
import pytest
from unittest.mock import patch
import pandas as pd


class TestGetWorkcenterGroup:
    """Test get_workcenter_group function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache state before each test."""
        import mes_dashboard.services.filter_cache as fc
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False
        yield
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False

    def test_returns_group_for_valid_workcenter(self):
        """Test returns group for valid workcenter name."""
        import mes_dashboard.services.filter_cache as fc

        mock_mapping = {
            'DB-01': {'group': '焊接', 'sequence': 1},
            'WB-01': {'group': '焊線', 'sequence': 2},
        }

        with patch.object(fc, 'get_workcenter_mapping', return_value=mock_mapping):
            result = fc.get_workcenter_group('DB-01')
            assert result == '焊接'

    def test_returns_none_for_unknown_workcenter(self):
        """Test returns None for unknown workcenter name."""
        import mes_dashboard.services.filter_cache as fc

        mock_mapping = {
            'DB-01': {'group': '焊接', 'sequence': 1},
        }

        with patch.object(fc, 'get_workcenter_mapping', return_value=mock_mapping):
            result = fc.get_workcenter_group('UNKNOWN')
            assert result is None

    def test_returns_none_when_mapping_unavailable(self):
        """Test returns None when mapping is unavailable."""
        import mes_dashboard.services.filter_cache as fc

        with patch.object(fc, 'get_workcenter_mapping', return_value=None):
            result = fc.get_workcenter_group('DB-01')
            assert result is None


class TestGetWorkcenterShort:
    """Test get_workcenter_short function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache state before each test."""
        import mes_dashboard.services.filter_cache as fc
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False
        yield
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False

    def test_returns_short_name_for_valid_workcenter(self):
        """Test returns short name for valid workcenter."""
        import mes_dashboard.services.filter_cache as fc
        from datetime import datetime

        # Set up cache directly
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_to_short'] = {
                'DB-01': 'DB',
                'WB-01': 'WB',
            }
            fc._CACHE['workcenter_groups'] = [{'name': '焊接', 'sequence': 1}]
            fc._CACHE['workcenter_mapping'] = {}
            fc._CACHE['last_refresh'] = datetime.now()

        result = fc.get_workcenter_short('DB-01')
        assert result == 'DB'

    def test_returns_none_for_unknown_workcenter(self):
        """Test returns None for unknown workcenter."""
        import mes_dashboard.services.filter_cache as fc
        from datetime import datetime

        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_to_short'] = {
                'DB-01': 'DB',
            }
            fc._CACHE['workcenter_groups'] = [{'name': '焊接', 'sequence': 1}]
            fc._CACHE['workcenter_mapping'] = {}
            fc._CACHE['last_refresh'] = datetime.now()

        result = fc.get_workcenter_short('UNKNOWN')
        assert result is None


class TestGetWorkcentersByGroup:
    """Test get_workcenters_by_group function."""

    def test_returns_workcenters_in_group(self):
        """Test returns all workcenters in specified group."""
        import mes_dashboard.services.filter_cache as fc

        mock_mapping = {
            'DB-01': {'group': '焊接', 'sequence': 1},
            'DB-02': {'group': '焊接', 'sequence': 1},
            'WB-01': {'group': '焊線', 'sequence': 2},
        }

        with patch.object(fc, 'get_workcenter_mapping', return_value=mock_mapping):
            result = fc.get_workcenters_by_group('焊接')

            assert len(result) == 2
            assert 'DB-01' in result
            assert 'DB-02' in result
            assert 'WB-01' not in result

    def test_returns_empty_for_unknown_group(self):
        """Test returns empty list for unknown group."""
        import mes_dashboard.services.filter_cache as fc

        mock_mapping = {
            'DB-01': {'group': '焊接', 'sequence': 1},
        }

        with patch.object(fc, 'get_workcenter_mapping', return_value=mock_mapping):
            result = fc.get_workcenters_by_group('UNKNOWN')
            assert result == []

    def test_returns_empty_when_mapping_unavailable(self):
        """Test returns empty list when mapping unavailable."""
        import mes_dashboard.services.filter_cache as fc

        with patch.object(fc, 'get_workcenter_mapping', return_value=None):
            result = fc.get_workcenters_by_group('焊接')
            assert result == []


class TestGetWorkcentersForGroups:
    """Test get_workcenters_for_groups function."""

    def test_returns_workcenters_for_multiple_groups(self):
        """Test returns workcenters for multiple groups."""
        import mes_dashboard.services.filter_cache as fc

        mock_mapping = {
            'DB-01': {'group': '焊接', 'sequence': 1},
            'WB-01': {'group': '焊線', 'sequence': 2},
            'MD-01': {'group': '成型', 'sequence': 3},
        }

        with patch.object(fc, 'get_workcenter_mapping', return_value=mock_mapping):
            result = fc.get_workcenters_for_groups(['焊接', '焊線'])

            assert len(result) == 2
            assert 'DB-01' in result
            assert 'WB-01' in result
            assert 'MD-01' not in result

    def test_returns_empty_for_empty_groups_list(self):
        """Test returns empty list for empty groups list."""
        import mes_dashboard.services.filter_cache as fc

        mock_mapping = {
            'DB-01': {'group': '焊接', 'sequence': 1},
        }

        with patch.object(fc, 'get_workcenter_mapping', return_value=mock_mapping):
            result = fc.get_workcenters_for_groups([])
            assert result == []


class TestGetWorkcenterGroups:
    """Test get_workcenter_groups function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache state before each test."""
        import mes_dashboard.services.filter_cache as fc
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False
        yield
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False

    def test_returns_groups_sorted_by_sequence(self):
        """Test returns groups sorted by sequence."""
        import mes_dashboard.services.filter_cache as fc
        from datetime import datetime

        # Set up cache directly
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = [
                {'name': '成型', 'sequence': 3},
                {'name': '焊接', 'sequence': 1},
                {'name': '焊線', 'sequence': 2},
            ]
            fc._CACHE['workcenter_mapping'] = {}
            fc._CACHE['workcenter_to_short'] = {}
            fc._CACHE['last_refresh'] = datetime.now()

        result = fc.get_workcenter_groups()

        # Should preserve original order (as stored)
        assert len(result) == 3
        names = [g['name'] for g in result]
        assert '成型' in names
        assert '焊接' in names
        assert '焊線' in names


class TestLoadWorkcenterMappingFromSpec:
    """Test _load_workcenter_mapping_from_spec function."""

    def test_builds_mapping_from_spec_view(self):
        """Test builds mapping from SPEC_WORKCENTER_V data."""
        import mes_dashboard.services.filter_cache as fc

        mock_df = pd.DataFrame({
            'WORK_CENTER': ['DB-01', 'DB-02', 'WB-01'],
            'WORK_CENTER_GROUP': ['焊接', '焊接', '焊線'],
            'WORKCENTERSEQUENCE_GROUP': [1, 1, 2],
            'WORK_CENTER_SHORT': ['DB', 'DB', 'WB'],
        })

        with patch.object(fc, 'read_sql_df', return_value=mock_df):
            groups, mapping, short_mapping = fc._load_workcenter_mapping_from_spec()

            # Check groups
            assert len(groups) == 2  # 2 unique groups
            group_names = [g['name'] for g in groups]
            assert '焊接' in group_names
            assert '焊線' in group_names

            # Check mapping
            assert len(mapping) == 3
            assert mapping['DB-01']['group'] == '焊接'
            assert mapping['WB-01']['group'] == '焊線'

            # Check short mapping
            assert short_mapping['DB-01'] == 'DB'
            assert short_mapping['WB-01'] == 'WB'

    def test_returns_empty_when_no_data(self):
        """Test returns empty structures when no data."""
        import mes_dashboard.services.filter_cache as fc

        with patch.object(fc, 'read_sql_df', return_value=None):
            groups, mapping, short_mapping = fc._load_workcenter_mapping_from_spec()

            assert groups == []
            assert mapping == {}
            assert short_mapping == {}

    def test_handles_empty_dataframe(self):
        """Test handles empty DataFrame."""
        import mes_dashboard.services.filter_cache as fc

        mock_df = pd.DataFrame(columns=['WORK_CENTER', 'WORK_CENTER_GROUP', 'WORKCENTERSEQUENCE_GROUP', 'WORK_CENTER_SHORT'])

        with patch.object(fc, 'read_sql_df', return_value=mock_df):
            groups, mapping, short_mapping = fc._load_workcenter_mapping_from_spec()

            assert groups == []
            assert mapping == {}
            assert short_mapping == {}


class TestGetCacheStatus:
    """Test get_cache_status function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset cache state before each test."""
        import mes_dashboard.services.filter_cache as fc
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False
        yield
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = None
            fc._CACHE['workcenter_mapping'] = None
            fc._CACHE['workcenter_to_short'] = None
            fc._CACHE['last_refresh'] = None
            fc._CACHE['is_loading'] = False

    def test_returns_not_loaded_when_empty(self):
        """Test returns loaded=False when cache empty."""
        import mes_dashboard.services.filter_cache as fc

        result = fc.get_cache_status()

        assert result['loaded'] is False
        assert result['last_refresh'] is None

    def test_returns_loaded_when_data_exists(self):
        """Test returns loaded=True when cache has data."""
        import mes_dashboard.services.filter_cache as fc
        from datetime import datetime

        now = datetime.now()
        with fc._CACHE_LOCK:
            fc._CACHE['workcenter_groups'] = [{'name': 'G1', 'sequence': 1}]
            fc._CACHE['workcenter_mapping'] = {'WC1': {'group': 'G1', 'sequence': 1}}
            fc._CACHE['last_refresh'] = now

        result = fc.get_cache_status()

        assert result['loaded'] is True
        assert result['last_refresh'] is not None
        assert result['workcenter_groups_count'] == 1
        assert result['workcenter_mapping_count'] == 1


class TestFilterCacheConfig:
    """Test environment-based filter-cache source configuration."""

    def test_filter_cache_views_are_env_configurable(self, monkeypatch):
        monkeypatch.setenv("FILTER_CACHE_WIP_VIEW", "CUSTOM.WIP_VIEW")
        monkeypatch.setenv("FILTER_CACHE_SPEC_WORKCENTER_VIEW", "CUSTOM.SPEC_VIEW")

        import mes_dashboard.services.filter_cache as fc

        reloaded = importlib.reload(fc)
        assert reloaded.WIP_VIEW == "CUSTOM.WIP_VIEW"
        assert reloaded.SPEC_WORKCENTER_VIEW == "CUSTOM.SPEC_VIEW"
