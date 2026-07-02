# -*- coding: utf-8 -*-
"""Integration test (AC-5): production_achievement_service must resolve
workcenter_group via the EXISTING services/filter_cache.get_spec_workcenter_mapping()
cache -- no new SPECNAME->station map is introduced (business-rules.md PA-06,
design.md Key Decisions).
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

pytestmark = pytest.mark.integration


class TestFilterCacheReuse:
    @patch("mes_dashboard.services.production_achievement_service.get_spec_workcenter_mapping")
    def test_service_calls_get_spec_workcenter_mapping_not_new_cache(self, mock_mapping):
        from mes_dashboard.services.production_achievement_service import build_achievement_rows

        mock_mapping.return_value = {
            "EPOXY D/B": {"workcenter": "WC1", "group": "焊接_DB", "sequence": 1},
        }
        df = pd.DataFrame(
            [{"OUTPUT_DATE": "2026-04-27", "SHIFT_CODE": "D", "SPECNAME": "Epoxy D/B", "ACTUAL_OUTPUT_QTY": 10}]
        )
        build_achievement_rows(df, targets={})

        mock_mapping.assert_called()

    def test_service_module_imports_get_spec_workcenter_mapping_from_filter_cache(self):
        """Static import-source assertion: the service must import the function
        from services.filter_cache (the existing cache), not redefine or
        hardcode a new SPECNAME map."""
        import mes_dashboard.services.production_achievement_service as svc
        import mes_dashboard.services.filter_cache as filter_cache

        assert svc.get_spec_workcenter_mapping is filter_cache.get_spec_workcenter_mapping
