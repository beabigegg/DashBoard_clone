"""Tests for SQL Loader."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from mes_dashboard.sql.loader import SQLLoader


class TestSQLLoader:
    """Test SQLLoader class."""

    def setup_method(self):
        """Clear cache before each test."""
        SQLLoader.clear_cache()

    def test_load_existing_file(self, tmp_path):
        """Test loading an existing SQL file."""
        # Create a temporary SQL file
        sql_dir = tmp_path / "wip"
        sql_dir.mkdir()
        sql_file = sql_dir / "summary.sql"
        sql_file.write_text("SELECT * FROM DWH.DW_MES_LOT_V")

        # Patch the _sql_dir to use our temp directory
        with patch.object(SQLLoader, "_sql_dir", tmp_path):
            result = SQLLoader.load("wip/summary")
            assert result == "SELECT * FROM DWH.DW_MES_LOT_V"

    def test_load_nonexistent_file(self):
        """Test loading a non-existent SQL file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError) as exc_info:
            SQLLoader.load("nonexistent/query")
        assert "SQL file not found" in str(exc_info.value)

    def test_load_uses_cache(self, tmp_path):
        """Test that repeated loads use the cache."""
        # Create a temporary SQL file
        sql_dir = tmp_path / "test"
        sql_dir.mkdir()
        sql_file = sql_dir / "cached.sql"
        sql_file.write_text("SELECT 1")

        with patch.object(SQLLoader, "_sql_dir", tmp_path):
            SQLLoader.clear_cache()

            # First load
            result1 = SQLLoader.load("test/cached")
            info1 = SQLLoader.cache_info()

            # Second load (should hit cache)
            result2 = SQLLoader.load("test/cached")
            info2 = SQLLoader.cache_info()

            assert result1 == result2
            assert info1.misses == 1
            assert info2.hits == 1

    def test_load_with_params_substitutes_values(self, tmp_path):
        """Test structural parameter substitution."""
        sql_dir = tmp_path
        sql_file = sql_dir / "query.sql"
        sql_file.write_text("SELECT * FROM {{ table_name }}")

        with patch.object(SQLLoader, "_sql_dir", tmp_path):
            result = SQLLoader.load_with_params("query", table_name="DWH.MY_TABLE")
            assert result == "SELECT * FROM DWH.MY_TABLE"

    def test_load_with_params_preserves_unsubstituted(self, tmp_path):
        """Test that unsubstituted parameters remain unchanged."""
        sql_dir = tmp_path
        sql_file = sql_dir / "query.sql"
        sql_file.write_text("SELECT * FROM {{ table_name }} {{ WHERE_CLAUSE }}")

        with patch.object(SQLLoader, "_sql_dir", tmp_path):
            result = SQLLoader.load_with_params("query", table_name="T")
            assert result == "SELECT * FROM T {{ WHERE_CLAUSE }}"

    def test_clear_cache(self, tmp_path):
        """Test cache clearing."""
        sql_dir = tmp_path
        sql_file = sql_dir / "test.sql"
        sql_file.write_text("SELECT 1")

        with patch.object(SQLLoader, "_sql_dir", tmp_path):
            SQLLoader.load("test")
            info_before = SQLLoader.cache_info()
            assert info_before.currsize > 0

            SQLLoader.clear_cache()
            info_after = SQLLoader.cache_info()
            assert info_after.currsize == 0

    def test_cache_info(self, tmp_path):
        """Test cache_info returns valid statistics."""
        sql_dir = tmp_path
        sql_file = sql_dir / "test.sql"
        sql_file.write_text("SELECT 1")

        with patch.object(SQLLoader, "_sql_dir", tmp_path):
            SQLLoader.clear_cache()
            SQLLoader.load("test")
            info = SQLLoader.cache_info()

            assert hasattr(info, "hits")
            assert hasattr(info, "misses")
            assert hasattr(info, "maxsize")
            assert hasattr(info, "currsize")
            assert info.maxsize == 100
