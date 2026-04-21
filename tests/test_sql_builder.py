"""Tests for Query Builder."""

import pytest

from mes_dashboard.sql.builder import QueryBuilder


class TestQueryBuilder:
    """Test QueryBuilder class."""

    def test_add_param_condition(self):
        """Test adding a parameterized condition."""
        builder = QueryBuilder()
        builder.add_param_condition("status", "RUN")

        assert len(builder.conditions) == 1
        assert "status = :p0" in builder.conditions[0]
        assert builder.params["p0"] == "RUN"

    def test_add_param_condition_with_operator(self):
        """Test adding a parameterized condition with custom operator."""
        builder = QueryBuilder()
        builder.add_param_condition("count", 10, operator=">=")

        assert "count >= :p0" in builder.conditions[0]
        assert builder.params["p0"] == 10

    def test_add_in_condition(self):
        """Test adding an IN condition."""
        builder = QueryBuilder()
        builder.add_in_condition("status", ["RUN", "QUEUE", "HOLD"])

        assert len(builder.conditions) == 1
        assert "status IN (:p0, :p1, :p2)" in builder.conditions[0]
        assert builder.params["p0"] == "RUN"
        assert builder.params["p1"] == "QUEUE"
        assert builder.params["p2"] == "HOLD"

    def test_add_in_condition_empty_list(self):
        """Test that empty list doesn't add condition."""
        builder = QueryBuilder()
        builder.add_in_condition("status", [])

        assert len(builder.conditions) == 0
        assert len(builder.params) == 0

    def test_add_not_in_condition(self):
        """Test adding a NOT IN condition."""
        builder = QueryBuilder()
        builder.add_not_in_condition("location", ["ATEC", "F區"])

        assert len(builder.conditions) == 1
        assert "location NOT IN (:p0, :p1)" in builder.conditions[0]
        assert builder.params["p0"] == "ATEC"
        assert builder.params["p1"] == "F區"

    def test_add_not_in_condition_with_null(self):
        """Test NOT IN condition allowing NULL values."""
        builder = QueryBuilder()
        builder.add_not_in_condition("location", ["ATEC"], allow_null=True)

        assert len(builder.conditions) == 1
        assert "(location IS NULL OR (location NOT IN (:p0)))" in builder.conditions[0]

    def test_add_like_condition_both(self):
        """Test LIKE condition with wildcards on both sides."""
        builder = QueryBuilder()
        builder.add_like_condition("name", "test")

        assert "name LIKE :p0 ESCAPE '\\'" in builder.conditions[0]
        assert builder.params["p0"] == "%test%"

    def test_add_like_condition_start(self):
        """Test LIKE condition with wildcard at end only."""
        builder = QueryBuilder()
        builder.add_like_condition("name", "prefix", position="start")

        assert builder.params["p0"] == "prefix%"

    def test_add_like_condition_end(self):
        """Test LIKE condition with wildcard at start only."""
        builder = QueryBuilder()
        builder.add_like_condition("name", "suffix", position="end")

        assert builder.params["p0"] == "%suffix"

    def test_add_like_condition_escapes_wildcards(self):
        """Test that LIKE condition escapes SQL wildcards."""
        builder = QueryBuilder()
        builder.add_like_condition("name", "test%value")

        assert builder.params["p0"] == "%test\\%value%"

    def test_add_like_condition_escapes_underscore(self):
        """Test that LIKE condition escapes underscores."""
        builder = QueryBuilder()
        builder.add_like_condition("name", "test_value")

        assert builder.params["p0"] == "%test\\_value%"

    def test_build_with_conditions(self):
        """Test building SQL with multiple conditions."""
        builder = QueryBuilder("SELECT * FROM t {{ WHERE_CLAUSE }}")
        builder.add_param_condition("status", "RUN")
        builder.add_in_condition("type", ["A", "B"])

        sql, params = builder.build()

        assert "WHERE" in sql
        assert "status = :p0" in sql
        assert "type IN (:p1, :p2)" in sql
        assert "AND" in sql
        assert params["p0"] == "RUN"
        assert params["p1"] == "A"
        assert params["p2"] == "B"

    def test_build_without_conditions(self):
        """Test building SQL with no conditions."""
        builder = QueryBuilder("SELECT * FROM t {{ WHERE_CLAUSE }}")
        sql, params = builder.build()

        assert "WHERE" not in sql
        assert "{{ WHERE_CLAUSE }}" not in sql
        assert params == {}

    def test_build_where_only(self):
        """Test building only the WHERE clause."""
        builder = QueryBuilder()
        builder.add_param_condition("status", "RUN")

        where_clause, params = builder.build_where_only()

        assert where_clause.startswith("WHERE")
        assert "status = :p0" in where_clause

    def test_get_conditions_sql(self):
        """Test getting conditions as string."""
        builder = QueryBuilder()
        builder.add_param_condition("a", 1)
        builder.add_param_condition("b", 2)

        conditions = builder.get_conditions_sql()

        assert "a = :p0 AND b = :p1" == conditions

    def test_reset(self):
        """Test resetting the builder."""
        builder = QueryBuilder("SELECT * FROM t")
        builder.add_param_condition("status", "RUN")
        builder.reset()

        assert len(builder.conditions) == 0
        assert len(builder.params) == 0
        assert builder._param_counter == 0
        assert builder.base_sql == "SELECT * FROM t"

    def test_method_chaining(self):
        """Test that methods support chaining."""
        builder = (
            QueryBuilder("SELECT * FROM t {{ WHERE_CLAUSE }}")
            .add_param_condition("status", "RUN")
            .add_in_condition("type", ["A", "B"])
            .add_like_condition("name", "test")
        )

        assert len(builder.conditions) == 3

    def test_add_is_null(self):
        """Test adding IS NULL condition."""
        builder = QueryBuilder()
        builder.add_is_null("deleted_at")

        assert "deleted_at IS NULL" in builder.conditions[0]

    def test_add_is_not_null(self):
        """Test adding IS NOT NULL condition."""
        builder = QueryBuilder()
        builder.add_is_not_null("updated_at")

        assert "updated_at IS NOT NULL" in builder.conditions[0]

    def test_add_condition_fixed(self):
        """Test adding a fixed condition."""
        builder = QueryBuilder()
        builder.add_condition("1=1")

        assert "1=1" in builder.conditions[0]
        assert len(builder.params) == 0

    def test_add_or_like_conditions(self):
        """Test adding multiple LIKE conditions combined with OR."""
        builder = QueryBuilder()
        builder.add_or_like_conditions("name", ["foo", "bar", "baz"])

        assert len(builder.conditions) == 1
        condition = builder.conditions[0]
        assert "name LIKE :p0 ESCAPE '\\'" in condition
        assert "name LIKE :p1 ESCAPE '\\'" in condition
        assert "name LIKE :p2 ESCAPE '\\'" in condition
        assert " OR " in condition
        assert condition.startswith("(")
        assert condition.endswith(")")
        assert builder.params["p0"] == "%foo%"
        assert builder.params["p1"] == "%bar%"
        assert builder.params["p2"] == "%baz%"

    def test_add_or_like_conditions_case_insensitive(self):
        """Test OR LIKE conditions with case insensitive matching."""
        builder = QueryBuilder()
        builder.add_or_like_conditions("name", ["Foo", "BAR"], case_insensitive=True)

        condition = builder.conditions[0]
        assert "UPPER(name)" in condition
        assert builder.params["p0"] == "%FOO%"
        assert builder.params["p1"] == "%BAR%"

    def test_add_or_like_conditions_escapes_wildcards(self):
        """Test OR LIKE conditions escape SQL wildcards."""
        builder = QueryBuilder()
        builder.add_or_like_conditions("name", ["test%val", "foo_bar"])

        assert builder.params["p0"] == "%test\\%val%"
        assert builder.params["p1"] == "%foo\\_bar%"

    def test_add_or_like_conditions_empty_list(self):
        """Test that empty list doesn't add condition."""
        builder = QueryBuilder()
        builder.add_or_like_conditions("name", [])

        assert len(builder.conditions) == 0
        assert len(builder.params) == 0

    def test_add_or_like_conditions_position(self):
        """Test OR LIKE conditions with different positions."""
        builder = QueryBuilder()
        builder.add_or_like_conditions("name", ["test"], position="start")

        assert builder.params["p0"] == "test%"
