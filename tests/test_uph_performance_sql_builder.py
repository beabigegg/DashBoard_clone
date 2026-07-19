# -*- coding: utf-8 -*-
"""Unit tests for the UPH Performance SQL/filter-builder functions.

Covers business-rules.md UPH-01..UPH-05 as structural pinning tests: assert
on the mapping/lookup mechanism itself, not just output values (test-plan.md
Notes) so a regression to prefix enumeration or reintroduced scale
conversion tripwires red.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

_SQL_PATH = (
    Path(__file__).parent.parent
    / "src" / "mes_dashboard" / "sql" / "uph_performance.sql"
)


# ---------------------------------------------------------------------------
# UPH-01: chunk window <=6h, LAST_UPDATE_TIME mandatory, unbounded range rejected
# ---------------------------------------------------------------------------

class TestChunkWindow:
    def test_chunk_window_never_exceeds_6h(self):
        from mes_dashboard.workers.uph_performance_worker import _build_time_chunks

        chunks = _build_time_chunks("2026-01-01", "2026-01-03")
        assert chunks, "expected at least one chunk"
        for chunk in chunks:
            start = _parse(chunk["chunk_start"])
            end = _parse(chunk["chunk_end"])
            assert end - start <= timedelta(hours=6), (
                f"chunk window exceeds 6h: {chunk}"
            )
            assert end > start

    def test_missing_last_update_time_raises_or_400(self):
        from mes_dashboard.services.uph_performance_service import (
            validate_uph_performance_params,
        )

        with pytest.raises(ValueError):
            validate_uph_performance_params(None, None)
        with pytest.raises(ValueError):
            validate_uph_performance_params("2026-01-01", None)

    def test_unbounded_date_range_rejected(self):
        """mirrors EA-03 / SYS-04: > 730 days is rejected."""
        from mes_dashboard.services.uph_performance_service import (
            validate_uph_performance_params,
        )

        with pytest.raises(ValueError):
            validate_uph_performance_params("2020-01-01", "2023-06-01")


def _parse(ts: str):
    from datetime import datetime
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# UPH-02: family scope restricted to GDBA/GWBA only
# ---------------------------------------------------------------------------

class TestFamilyScope:
    def test_family_scope_restricted_to_gdba_gwba(self):
        from mes_dashboard.workers.uph_performance_worker import _build_family_filter

        assert _build_family_filter([]) == (
            "(e.EQUIPMENT_ID LIKE 'GDBA%' OR e.EQUIPMENT_ID LIKE 'GWBA%')"
        )
        assert _build_family_filter(["GDBA"]) == "e.EQUIPMENT_ID LIKE 'GDBA%'"
        assert _build_family_filter(["GWBA"]) == "e.EQUIPMENT_ID LIKE 'GWBA%'"
        assert _build_family_filter(["GDBA", "GWBA"]) == (
            "(e.EQUIPMENT_ID LIKE 'GDBA%' OR e.EQUIPMENT_ID LIKE 'GWBA%')"
        )

    def test_family_outside_gdba_gwba_returns_400(self):
        """GWBK/GWMT/GPTA and any other family outside {GDBA, GWBA} -> 400 (UPH-02)."""
        from mes_dashboard.services.uph_performance_service import (
            validate_uph_performance_params,
        )

        for bad_family in ("GWBK", "GWMT", "GPTA"):
            with pytest.raises(ValueError):
                validate_uph_performance_params(
                    "2026-01-01", "2026-01-02", families=[bad_family]
                )


# ---------------------------------------------------------------------------
# 機型 (RESOURCEFAMILYNAME) coarse filter -- the real machine-model axis that
# replaced the GDBA/GWBA-only selector (add-uph-performance-page redesign)
# ---------------------------------------------------------------------------

class TestModelsFilter:
    def test_empty_models_yields_no_clause(self):
        from mes_dashboard.workers.uph_performance_worker import _build_models_exists_filter

        assert _build_models_exists_filter([]) == ("", {})
        assert _build_models_exists_filter(None) == ("", {})

    def test_models_build_exists_semijoin_on_resourcefamilyname(self):
        from mes_dashboard.workers.uph_performance_worker import _build_models_exists_filter

        clause, params = _build_models_exists_filter(["DBA_AD832UR", "WBA_iHawk"])
        assert "EXISTS (SELECT 1 FROM DWH.DW_MES_RESOURCE r" in clause
        assert "r.RESOURCENAME = e.EQUIPMENT_ID" in clause
        assert "r.RESOURCEFAMILYNAME" in clause
        assert ":mdl_0" in clause and ":mdl_1" in clause
        assert params == {"mdl_0": "DBA_AD832UR", "mdl_1": "WBA_iHawk"}
        # No embedded newline -- would corrupt the template's header comment
        # (SQLLoader.load_with_params global replace, ORA-00900 trap).
        assert "\n" not in clause

    def test_models_participate_in_spool_key(self):
        from mes_dashboard.services.uph_performance_cache import make_uph_performance_spool_key

        base = make_uph_performance_spool_key("2026-01-01", "2026-01-01")
        with_model = make_uph_performance_spool_key("2026-01-01", "2026-01-01", models=["DBA_AD832UR"])
        assert base != with_model, "models must be part of the spool key so model-filtered queries don't collide"


# ---------------------------------------------------------------------------
# UPH-03: family -> PARAMETER_NAME mapping pinned; swap-detection
# ---------------------------------------------------------------------------

class TestParameterNameMapping:
    def test_gdba_maps_to_bonduph_parameter_name(self):
        from mes_dashboard.workers.uph_performance_worker import FAMILY_PARAMETER_MAP

        assert FAMILY_PARAMETER_MAP["GDBA"] == "BondUPH"

    def test_gwba_maps_to_fhcm_uph_parameter_name(self):
        from mes_dashboard.workers.uph_performance_worker import FAMILY_PARAMETER_MAP

        assert FAMILY_PARAMETER_MAP["GWBA"] == "fHCM_UPH"

    def test_parameter_mapping_swap_detected(self):
        """Fails if the GDBA/GWBA -> PARAMETER_NAME mapping is ever swapped.

        Reads the actual executed SQL artifact (not just the Python dict) so
        a regression in the shipped .sql template itself is caught (ADR-0017
        Decision-1: exact-match CASE, never a blanket IN-list).
        """
        sql_text = _SQL_PATH.read_text(encoding="utf-8")

        assert "WHEN 'GDBA' THEN 'BondUPH'" in sql_text
        assert "WHEN 'GWBA' THEN 'fHCM_UPH'" in sql_text
        assert "WHEN 'GDBA' THEN 'fHCM_UPH'" not in sql_text
        assert "WHEN 'GWBA' THEN 'BondUPH'" not in sql_text

        # Never a blanket IN-list leaking one family's parameter to the other
        # (checked against the executable ON-clause predicate, not the
        # explanatory prose comment above it which quotes this exact string
        # as the rejected alternative).
        assert "d.PARAMETER_NAME IN (" not in sql_text
        assert "d.PARAMETER_NAME = CASE" in sql_text

        from mes_dashboard.workers.uph_performance_worker import FAMILY_PARAMETER_MAP

        assert FAMILY_PARAMETER_MAP == {"GDBA": "BondUPH", "GWBA": "fHCM_UPH"}


# ---------------------------------------------------------------------------
# UPH-04: no scale conversion on UPH_VALUE
# ---------------------------------------------------------------------------

class TestNoScaleConversion:
    def test_uph_value_no_scale_conversion(self):
        """UPH-04: PARAMETER_VALUE must be used as-is -- no x100 / div-by-100 anywhere."""
        from mes_dashboard.workers.uph_performance_worker import _build_final_select_sql

        final_sql = _build_final_select_sql("abcd1234")

        assert "TRY_CAST(e.UPH_VALUE_RAW AS DOUBLE)" in final_sql
        assert "* 100" not in final_sql
        assert "/ 100" not in final_sql
        assert "*100" not in final_sql
        assert "/100" not in final_sql

        sql_text = _SQL_PATH.read_text(encoding="utf-8")
        assert "* 100" not in sql_text
        assert "/ 100" not in sql_text


# ---------------------------------------------------------------------------
# UPH-05: DB/WB label via workcenter_groups, not EQUIPMENT_ID prefix enumeration
# ---------------------------------------------------------------------------

class TestDbWbLabel:
    def test_db_wb_label_via_workcenter_groups_not_prefix(self):
        """Mirrors EA-07 regression class: must use workcenter_groups.get_workcenter_group(),
        never a closed EQUIPMENT_ID prefix enumeration (e.g. GDBA%->DB, GWBA%->WB)."""
        import inspect
        import mes_dashboard.workers.uph_performance_worker as w

        assert w._compute_db_wb_label("焊接_DB_1線") == "焊接_DB"
        assert w._compute_db_wb_label("焊接_WB_2線") == "焊接_WB"

        source = inspect.getsource(w._compute_db_wb_label)
        assert "get_workcenter_group" in source
        assert "GDBA" not in source
        assert "GWBA" not in source
        assert "EQUIPMENT_ID" not in source

    def test_db_wb_label_null_when_workcenter_unmapped(self):
        import mes_dashboard.workers.uph_performance_worker as w

        assert w._compute_db_wb_label("某未知站點") is None
        assert w._compute_db_wb_label(None) is None
        assert w._compute_db_wb_label("") is None


# ---------------------------------------------------------------------------
# Regression: full-template render must never leave a header comment line
# uncommented, regardless of how many coarse filters are active.
#
# Root cause (reproduced live as ORA-00900 against real Oracle during initial
# build): SQLLoader.load_with_params substitutes `{{ NAME }}` via a plain
# GLOBAL string replace, which also matches this template's own doc-comment
# mention of each placeholder. The extra-filter builder functions used to
# return fragments starting with "\n  AND ...". When ANY extra filter was
# active, that embedded newline got spliced into the header comment too,
# splitting a single `--` line in two and leaving the back half uncommented
# -- Oracle then rejected the whole statement as unparseable. Fixed by (a)
# never returning an embedded newline from the builder functions (the
# concatenation site in `pre_query` adds the newline only once, at the real
# WHERE-clause injection point) and (b) never spelling out the literal
# `{{ NAME }}` token in the template's own prose.
# ---------------------------------------------------------------------------

class TestFullTemplateRenderNeverCorruptsHeaderComment:
    def _render(self, family_filter: str, extra_filters: str) -> str:
        from mes_dashboard.sql import SQLLoader

        return SQLLoader.load_with_params(
            "uph_performance", FAMILY_FILTER=family_filter, EXTRA_FILTERS=extra_filters,
        )

    def _assert_header_intact(self, sql: str) -> None:
        lines = sql.split("\n")
        first_select = next(i for i, l in enumerate(lines) if l.strip().startswith("SELECT"))
        header_lines = lines[:first_select]
        for line in header_lines:
            if line.strip():
                assert line.lstrip().startswith("--"), (
                    "header comment line was split/uncommented by placeholder "
                    f"substitution: {line!r}"
                )

    def test_builder_functions_never_return_embedded_newline(self):
        from mes_dashboard.workers.uph_performance_worker import (
            _build_equipment_ids_filter,
            _build_container_exists_filter,
            _build_workcenter_names_exists_filter,
        )

        eq_clause, _ = _build_equipment_ids_filter(["GDBA-0001"])
        pjt_clause, _ = _build_container_exists_filter(["T"], "PJ_TYPE", "pjt")
        pkg_clause, _ = _build_container_exists_filter(["P"], "PRODUCTLINENAME", "pkg")
        wc_clause, _ = _build_workcenter_names_exists_filter(["W"])

        for clause in (eq_clause, pjt_clause, pkg_clause, wc_clause):
            assert "\n" not in clause, f"builder fragment must not embed a newline: {clause!r}"

    def test_header_comment_intact_with_no_extra_filters(self):
        sql = self._render("(e.EQUIPMENT_ID LIKE 'GDBA%' OR e.EQUIPMENT_ID LIKE 'GWBA%')", "")
        self._assert_header_intact(sql)

    def test_header_comment_intact_with_all_extra_filters_combined(self):
        from mes_dashboard.workers.uph_performance_worker import (
            _build_equipment_ids_filter,
            _build_container_exists_filter,
            _build_workcenter_names_exists_filter,
        )

        eq_clause, _ = _build_equipment_ids_filter(["GDBA-0001"])
        pjt_clause, _ = _build_container_exists_filter(["T"], "PJ_TYPE", "pjt")
        pkg_clause, _ = _build_container_exists_filter(["P"], "PRODUCTLINENAME", "pkg")
        wc_clause, _ = _build_workcenter_names_exists_filter(["W"])
        extra_filters = "".join(
            f"\n  {c}" for c in (eq_clause, pjt_clause, pkg_clause, wc_clause) if c
        )

        sql = self._render("e.EQUIPMENT_ID LIKE 'GDBA%'", extra_filters)
        self._assert_header_intact(sql)
        # And the real WHERE clause still gets every combined fragment, correctly separated.
        assert "AND e.EQUIPMENT_ID IN (:eqid_0)" in sql
        assert "AND EXISTS (SELECT 1 FROM DWH.DW_MES_CONTAINER c" in sql
        assert "AND EXISTS (SELECT 1 FROM DWH.DW_MES_RESOURCE r" in sql

    def test_template_prose_never_spells_out_literal_placeholder_braces(self):
        """The doc-comment HEADER (before the real SELECT) must never contain
        the literal "{{ NAME }}" token -- SQLLoader's global replace would
        otherwise re-corrupt it the moment someone reintroduces a placeholder
        mention in prose. The real SQL body legitimately needs these exact
        tokens (that's the actual substitution site) -- only the header is
        constrained here."""
        sql_text = _SQL_PATH.read_text(encoding="utf-8")
        lines = sql_text.split("\n")
        first_select = next(i for i, l in enumerate(lines) if l.strip().startswith("SELECT"))
        header_text = "\n".join(lines[:first_select])
        assert "{{ FAMILY_FILTER }}" not in header_text
        assert "{{ EXTRA_FILTERS }}" not in header_text
