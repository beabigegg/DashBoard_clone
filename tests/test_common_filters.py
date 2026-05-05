"""Tests for Common Filters."""

from unittest.mock import patch

from mes_dashboard.sql.builder import QueryBuilder
from mes_dashboard.sql.filters import CommonFilters, NON_QUALITY_HOLD_REASONS


class TestCommonFilters:
    """Test CommonFilters class."""

    def test_add_location_exclusion(self):
        """Test location exclusion filter."""
        builder = QueryBuilder()

        with patch(
            "mes_dashboard.sql.filters.EXCLUDED_LOCATIONS", ["ATEC", "F區"]
        ):
            CommonFilters.add_location_exclusion(builder)

        assert len(builder.conditions) == 1
        assert "LOCATIONNAME IS NULL OR (LOCATIONNAME NOT IN" in builder.conditions[0]
        assert builder.params["p0"] == "ATEC"
        assert builder.params["p1"] == "F區"

    def test_add_location_exclusion_empty(self):
        """Test location exclusion with empty list."""
        builder = QueryBuilder()

        with patch("mes_dashboard.sql.filters.EXCLUDED_LOCATIONS", []):
            CommonFilters.add_location_exclusion(builder)

        assert len(builder.conditions) == 0

    def test_add_location_exclusion_custom_column(self):
        """Test location exclusion with custom column name."""
        builder = QueryBuilder()

        with patch(
            "mes_dashboard.sql.filters.EXCLUDED_LOCATIONS", ["TEST"]
        ):
            CommonFilters.add_location_exclusion(builder, column="LOC_NAME")

        assert "LOC_NAME IS NULL OR (LOC_NAME NOT IN" in builder.conditions[0]

    def test_add_asset_status_exclusion(self):
        """Test asset status exclusion filter."""
        builder = QueryBuilder()

        with patch(
            "mes_dashboard.sql.filters.EXCLUDED_ASSET_STATUSES", ["報廢", "閒置"]
        ):
            CommonFilters.add_asset_status_exclusion(builder)

        assert len(builder.conditions) == 1
        assert "PJ_ASSETSSTATUS IS NULL OR (PJ_ASSETSSTATUS NOT IN" in builder.conditions[0]

    def test_add_asset_status_exclusion_empty(self):
        """Test asset status exclusion with empty list."""
        builder = QueryBuilder()

        with patch("mes_dashboard.sql.filters.EXCLUDED_ASSET_STATUSES", []):
            CommonFilters.add_asset_status_exclusion(builder)

        assert len(builder.conditions) == 0

    def test_add_wip_base_filters_workorder(self):
        """Test WIP base filter for workorder."""
        builder = QueryBuilder()
        CommonFilters.add_wip_base_filters(builder, workorder="WO123")

        assert len(builder.conditions) == 1
        assert "WORKORDER LIKE" in builder.conditions[0]
        assert "%WO123%" in builder.params["p0"]

    def test_add_wip_base_filters_lotid(self):
        """Test WIP base filter for lot ID."""
        builder = QueryBuilder()
        CommonFilters.add_wip_base_filters(builder, lotid="LOT001")

        assert len(builder.conditions) == 1
        assert "LOTID LIKE" in builder.conditions[0]

    def test_add_wip_base_filters_multiple(self):
        """Test WIP base filter with multiple parameters."""
        builder = QueryBuilder()
        CommonFilters.add_wip_base_filters(
            builder, workorder="WO", package="PKG", pj_type="TYPE"
        )

        assert len(builder.conditions) == 3
        assert any("WORKORDER LIKE" in c for c in builder.conditions)
        assert any("PACKAGE_LEF LIKE" in c for c in builder.conditions)
        assert any("PJ_TYPE LIKE" in c for c in builder.conditions)

    def test_add_status_filter_single(self):
        """Test status filter with single status."""
        builder = QueryBuilder()
        CommonFilters.add_status_filter(builder, status="HOLD")

        assert len(builder.conditions) == 1
        assert "STATUS = :p0" in builder.conditions[0]
        assert builder.params["p0"] == "HOLD"

    def test_add_status_filter_multiple(self):
        """Test status filter with multiple statuses."""
        builder = QueryBuilder()
        CommonFilters.add_status_filter(builder, statuses=["RUN", "QUEUE"])

        assert len(builder.conditions) == 1
        assert "STATUS IN (:p0, :p1)" in builder.conditions[0]
        assert builder.params["p0"] == "RUN"
        assert builder.params["p1"] == "QUEUE"

    def test_add_hold_type_filter_quality(self):
        """Test hold type filter for quality holds."""
        builder = QueryBuilder()
        CommonFilters.add_hold_type_filter(builder, hold_type="quality")

        assert len(builder.conditions) == 1
        assert "HOLDREASONNAME NOT IN" in builder.conditions[0]

    def test_add_hold_type_filter_non_quality(self):
        """Test hold type filter for non-quality holds."""
        builder = QueryBuilder()
        CommonFilters.add_hold_type_filter(builder, hold_type="non_quality")

        assert len(builder.conditions) == 1
        assert "HOLDREASONNAME IN" in builder.conditions[0]

    def test_is_quality_hold(self):
        """Test is_quality_hold helper function."""
        # Quality hold (not in non-quality list)
        assert CommonFilters.is_quality_hold("品質異常") is True

        # Non-quality hold (in list)
        non_quality_reason = list(NON_QUALITY_HOLD_REASONS)[0]
        assert CommonFilters.is_quality_hold(non_quality_reason) is False

    def test_add_equipment_filter_resource_ids(self):
        """Test equipment filter with resource IDs."""
        builder = QueryBuilder()
        CommonFilters.add_equipment_filter(builder, resource_ids=["R001", "R002"])

        assert len(builder.conditions) == 1
        assert "RESOURCEID IN" in builder.conditions[0]

    def test_add_equipment_filter_workcenters(self):
        """Test equipment filter with workcenters."""
        builder = QueryBuilder()
        CommonFilters.add_equipment_filter(builder, workcenters=["WC1", "WC2"])

        assert len(builder.conditions) == 1
        assert "WORKCENTERNAME IN" in builder.conditions[0]

    def test_build_location_filter_legacy(self):
        """Test legacy location filter builder."""
        result = CommonFilters.build_location_filter_legacy(
            locations=["LOC1", "LOC2"],
            excluded_locations=["EXC1"],
        )

        assert "LOCATIONNAME IN ('LOC1', 'LOC2')" in result
        assert "LOCATIONNAME NOT IN ('EXC1')" in result

    def test_build_asset_status_filter_legacy(self):
        """Test legacy asset status filter builder."""
        result = CommonFilters.build_asset_status_filter_legacy(
            excluded_statuses=["報廢", "閒置"]
        )

        assert "PJ_ASSETSSTATUS NOT IN" in result
        assert "'報廢'" in result
        assert "'閒置'" in result

    def test_build_asset_status_filter_legacy_empty(self):
        """Test legacy asset status filter with empty list."""
        result = CommonFilters.build_asset_status_filter_legacy(excluded_statuses=[])

        assert result == ""

    def test_non_quality_hold_reasons_exists(self):
        """Test that NON_QUALITY_HOLD_REASONS is defined and has content."""
        assert len(NON_QUALITY_HOLD_REASONS) > 0
        assert isinstance(NON_QUALITY_HOLD_REASONS, set)
