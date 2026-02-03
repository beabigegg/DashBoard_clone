"""
Query Builder

Provides safe SQL query building with parameterized conditions.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class QueryBuilder:
    """
    Safe SQL query builder with parameterized conditions.

    Builds WHERE clauses with Oracle bind variables (:param_name)
    to prevent SQL injection.
    """

    base_sql: str = ""
    conditions: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    _param_counter: int = field(default=0, repr=False)

    def _next_param(self) -> str:
        """Generate next parameter name."""
        name = f"p{self._param_counter}"
        self._param_counter += 1
        return name

    def add_condition(self, condition: str) -> "QueryBuilder":
        """
        Add a fixed condition (no parameters).

        Args:
            condition: SQL condition string

        Returns:
            self for method chaining
        """
        self.conditions.append(condition)
        return self

    def add_param_condition(
        self,
        column: str,
        value: Any,
        operator: str = "=",
    ) -> "QueryBuilder":
        """
        Add a parameterized condition.

        Args:
            column: Column name
            value: Value to compare
            operator: Comparison operator (default: "=")

        Returns:
            self for method chaining
        """
        param_name = self._next_param()
        self.conditions.append(f"{column} {operator} :{param_name}")
        self.params[param_name] = value
        return self

    def add_in_condition(
        self,
        column: str,
        values: List[Any],
    ) -> "QueryBuilder":
        """
        Add an IN condition with parameterized values.

        Args:
            column: Column name
            values: List of values for IN clause

        Returns:
            self for method chaining
        """
        if not values:
            return self

        param_names = []
        for val in values:
            param_name = self._next_param()
            param_names.append(f":{param_name}")
            self.params[param_name] = val

        self.conditions.append(f"{column} IN ({', '.join(param_names)})")
        return self

    def add_not_in_condition(
        self,
        column: str,
        values: List[Any],
        allow_null: bool = False,
    ) -> "QueryBuilder":
        """
        Add a NOT IN condition with parameterized values.

        Args:
            column: Column name
            values: List of values to exclude
            allow_null: If True, also allows NULL values

        Returns:
            self for method chaining
        """
        if not values:
            return self

        param_names = []
        for val in values:
            param_name = self._next_param()
            param_names.append(f":{param_name}")
            self.params[param_name] = val

        not_in_clause = f"{column} NOT IN ({', '.join(param_names)})"

        if allow_null:
            self.conditions.append(f"({column} IS NULL OR {not_in_clause})")
        else:
            self.conditions.append(not_in_clause)

        return self

    def add_like_condition(
        self,
        column: str,
        value: str,
        position: str = "both",
    ) -> "QueryBuilder":
        """
        Add a LIKE condition with escaped wildcards.

        Args:
            column: Column name
            value: Search value (wildcards will be escaped)
            position: Where to add wildcards:
                - "both": %value%
                - "start": value%
                - "end": %value

        Returns:
            self for method chaining
        """
        # Escape SQL LIKE wildcards
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

        if position == "both":
            pattern = f"%{escaped}%"
        elif position == "start":
            pattern = f"{escaped}%"
        elif position == "end":
            pattern = f"%{escaped}"
        else:
            pattern = escaped

        param_name = self._next_param()
        self.conditions.append(f"{column} LIKE :{param_name} ESCAPE '\\'")
        self.params[param_name] = pattern

        return self

    def add_or_like_conditions(
        self,
        column: str,
        values: List[str],
        position: str = "both",
        case_insensitive: bool = False,
    ) -> "QueryBuilder":
        """
        Add multiple LIKE conditions combined with OR.

        Args:
            column: Column name
            values: List of search values (wildcards will be escaped)
            position: Where to add wildcards (both/start/end)
            case_insensitive: If True, use UPPER() for case-insensitive matching

        Returns:
            self for method chaining
        """
        if not values:
            return self

        like_conditions = []
        col_expr = f"UPPER({column})" if case_insensitive else column

        for val in values:
            # Escape SQL LIKE wildcards
            escaped = val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            if case_insensitive:
                escaped = escaped.upper()

            if position == "both":
                pattern = f"%{escaped}%"
            elif position == "start":
                pattern = f"{escaped}%"
            elif position == "end":
                pattern = f"%{escaped}"
            else:
                pattern = escaped

            param_name = self._next_param()
            like_conditions.append(f"{col_expr} LIKE :{param_name} ESCAPE '\\'")
            self.params[param_name] = pattern

        self.conditions.append(f"({' OR '.join(like_conditions)})")
        return self

    def add_is_null(self, column: str) -> "QueryBuilder":
        """Add IS NULL condition."""
        self.conditions.append(f"{column} IS NULL")
        return self

    def add_is_not_null(self, column: str) -> "QueryBuilder":
        """Add IS NOT NULL condition."""
        self.conditions.append(f"{column} IS NOT NULL")
        return self

    def build(self) -> Tuple[str, Dict[str, Any]]:
        """
        Build the final SQL with WHERE clause.

        Replaces {{ WHERE_CLAUSE }} placeholder in base_sql.
        If no conditions, placeholder is replaced with empty string.

        Returns:
            Tuple of (sql_string, params_dict)
        """
        if self.conditions:
            where_clause = f"WHERE {' AND '.join(self.conditions)}"
        else:
            where_clause = ""

        sql = self.base_sql.replace("{{ WHERE_CLAUSE }}", where_clause)
        return sql, self.params.copy()

    def build_where_only(self) -> Tuple[str, Dict[str, Any]]:
        """
        Build only the WHERE clause (without base SQL).

        Returns:
            Tuple of (where_clause, params_dict)
        """
        if self.conditions:
            where_clause = f"WHERE {' AND '.join(self.conditions)}"
        else:
            where_clause = ""
        return where_clause, self.params.copy()

    def get_conditions_sql(self) -> str:
        """Get conditions as AND-joined string (without WHERE keyword)."""
        return " AND ".join(self.conditions) if self.conditions else ""

    def reset(self) -> "QueryBuilder":
        """Reset conditions and params, keep base_sql."""
        self.conditions = []
        self.params = {}
        self._param_counter = 0
        return self
