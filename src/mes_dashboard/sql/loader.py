"""
SQL File Loader

Provides SQL file loading with LRU caching and structural parameter substitution.
"""

from functools import lru_cache
from pathlib import Path


class SQLLoader:
    """SQL file loader with LRU caching."""

    _sql_dir: Path = Path(__file__).parent

    @classmethod
    @lru_cache(maxsize=100)
    def load(cls, name: str) -> str:
        """
        Load SQL file content.

        Args:
            name: SQL file path without extension, e.g., "wip/summary"

        Returns:
            SQL file content as string

        Raises:
            FileNotFoundError: If SQL file does not exist
        """
        path = cls._sql_dir / f"{name}.sql"
        if not path.exists():
            raise FileNotFoundError(f"SQL file not found: {path}")
        return path.read_text(encoding="utf-8")

    @classmethod
    def load_with_params(cls, name: str, **kwargs) -> str:
        """
        Load SQL file and substitute structural parameters.

        Uses Jinja2-style placeholders: {{ param_name }}
        Only use for structural parameters (table names, column lists),
        NOT for user input values.

        Args:
            name: SQL file path without extension
            **kwargs: Parameters to substitute

        Returns:
            SQL content with substituted parameters
        """
        sql = cls.load(name)
        for key, value in kwargs.items():
            sql = sql.replace(f"{{{{ {key} }}}}", str(value))
        return sql

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the LRU cache."""
        cls.load.cache_clear()

    @classmethod
    def cache_info(cls):
        """Get cache statistics."""
        return cls.load.cache_info()
