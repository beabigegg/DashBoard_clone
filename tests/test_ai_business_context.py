# -*- coding: utf-8 -*-
"""Unit tests for ai_business_context.py — business context constants for LLM prompts."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mes_dashboard.services import ai_business_context


class TestSystemOverview:
    def test_system_overview_is_string(self):
        assert isinstance(ai_business_context.SYSTEM_OVERVIEW, str)

    def test_system_overview_not_empty(self):
        assert len(ai_business_context.SYSTEM_OVERVIEW) > 100

    def test_system_overview_mentions_mes(self):
        assert "MES" in ai_business_context.SYSTEM_OVERVIEW

    def test_system_overview_distinguishes_realtime_vs_history(self):
        content = ai_business_context.SYSTEM_OVERVIEW
        assert "即時" in content or "View" in content
        assert "歷史" in content or "HISTORY" in content


class TestBusinessTerminology:
    def test_business_terminology_is_string(self):
        assert isinstance(ai_business_context.BUSINESS_TERMINOLOGY, str)

    def test_business_terminology_not_empty(self):
        assert len(ai_business_context.BUSINESS_TERMINOLOGY) > 50

    def test_business_terminology_mentions_equipment_id_format(self):
        content = ai_business_context.BUSINESS_TERMINOLOGY
        assert "GWXX" in content or "GWBK" in content or "GW" in content

    def test_business_terminology_mentions_hold_reason_codes(self):
        content = ai_business_context.BUSINESS_TERMINOLOGY
        assert "S1" in content or "Hold" in content or "HOLD" in content


class TestModuleExports:
    def test_module_has_system_overview(self):
        assert hasattr(ai_business_context, "SYSTEM_OVERVIEW")

    def test_module_has_business_terminology(self):
        assert hasattr(ai_business_context, "BUSINESS_TERMINOLOGY")

    def test_both_constants_are_non_empty_strings(self):
        for attr in ("SYSTEM_OVERVIEW", "BUSINESS_TERMINOLOGY"):
            val = getattr(ai_business_context, attr)
            assert isinstance(val, str) and val.strip(), f"{attr} must be a non-empty string"
