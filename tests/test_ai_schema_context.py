# -*- coding: utf-8 -*-
"""Unit tests for ai_schema_context module.

Covers:
- All 22 authorized tables are present in at least one domain
- TABLE_SCHEMAS covers all tables in TABLE_DOMAINS
- Schema columns exist in data/table_schema_info.json
- SQL_EXAMPLES are valid SELECT statements with FETCH FIRST
- Helper functions get_schemas_for_domains / get_examples_for_domains
"""

import json
import re
import unittest
from pathlib import Path

from mes_dashboard.services.ai_schema_context import (
    SQL_EXAMPLES,
    TABLE_DOMAINS,
    TABLE_SCHEMAS,
    get_examples_for_domains,
    get_schemas_for_domains,
)

_SCHEMA_FILE = Path(__file__).resolve().parent.parent / "data" / "table_schema_info.json"

# 22 authorized tables from docs/Oracle_Authorized_Objects.md
_AUTHORIZED_TABLES = {
    "DWH.DW_MES_CONTAINER",
    "DWH.DW_MES_EQUIPMENTSTATUS_WIP_V",
    "DWH.DW_MES_HM_LOTMOVEOUT",
    "DWH.DW_MES_HOLDRELEASEHISTORY",
    "DWH.DW_MES_JOB",
    "DWH.DW_MES_JOBTXNHISTORY",
    "DWH.DW_MES_LOTMATERIALSHISTORY",
    "DWH.DW_MES_LOTREJECTHISTORY",
    "DWH.DW_MES_LOTWIPDATAHISTORY",
    "DWH.DW_MES_LOTWIPHISTORY",
    "DWH.DW_MES_LOT_V",
    "DWH.DW_MES_MAINTENANCE",
    "DWH.DW_MES_PARTREQUESTORDER",
    "DWH.DW_MES_PJ_COMBINEDASSYLOTS",
    "DWH.DW_MES_RESOURCE",
    "DWH.DW_MES_RESOURCESTATUS",
    "DWH.DW_MES_RESOURCESTATUS_SHIFT",
    "DWH.DW_MES_SPEC_WORKCENTER_V",
    "DWH.DW_MES_WIP",
    "DWH.ERP_PJ_WIP_SCRAP_REASONS_EXCLUDE",
    "DWH.ERP_WIP_MOVETXN",
    "DWH.ERP_WIP_MOVETXN_DETAIL",
}


class TestTableDomains(unittest.TestCase):
    def test_required_domain_keys_present(self) -> None:
        required = {
            "wip_realtime", "lot_history", "reject", "hold", "equipment",
            "material", "job", "genealogy", "yield", "wip_data",
        }
        self.assertTrue(required.issubset(set(TABLE_DOMAINS.keys())))

    def test_all_authorized_tables_covered(self) -> None:
        covered: set[str] = set()
        for domain_def in TABLE_DOMAINS.values():
            covered.update(domain_def.get("tables", []))
        missing = _AUTHORIZED_TABLES - covered
        self.assertEqual(
            missing, set(),
            f"These authorized tables are not in any domain: {missing}",
        )

    def test_domain_entries_have_required_fields(self) -> None:
        for key, entry in TABLE_DOMAINS.items():
            self.assertIn("tables", entry, f"Domain '{key}' missing 'tables'")
            self.assertIn("description", entry, f"Domain '{key}' missing 'description'")
            self.assertIsInstance(entry["tables"], list)
            self.assertTrue(len(entry["tables"]) > 0, f"Domain '{key}' has empty tables list")


class TestTableSchemas(unittest.TestCase):
    def test_all_authorized_tables_have_schema(self) -> None:
        missing = _AUTHORIZED_TABLES - set(TABLE_SCHEMAS.keys())
        self.assertEqual(
            missing, set(),
            f"These authorized tables are missing from TABLE_SCHEMAS: {missing}",
        )

    def test_schema_columns_exist_in_schema_info(self) -> None:
        schema_info = json.loads(_SCHEMA_FILE.read_text(encoding="utf-8"))
        # Build a lookup: short_table_name -> set of column names
        col_lookup: dict[str, set[str]] = {}
        for short_name, info in schema_info.items():
            cols = {col["column_name"] for col in info.get("schema", [])}
            col_lookup[short_name] = cols

        for full_tbl, schema_str in TABLE_SCHEMAS.items():
            # Derive short name: strip DWH. prefix
            short_name = full_tbl.replace("DWH.", "")
            if short_name not in col_lookup:
                continue  # table not in schema_info, skip

            valid_cols = col_lookup[short_name]
            # Extract column names from schema string (first token of each non-comment line)
            for line in schema_str.splitlines():
                line = line.strip()
                if not line or line.startswith("--"):
                    continue
                col_name = line.split()[0]
                # Skip lines that start with lowercase (metadata lines)
                if col_name[0].islower():
                    continue
                self.assertIn(
                    col_name, valid_cols,
                    f"Column '{col_name}' in TABLE_SCHEMAS['{full_tbl}'] "
                    f"not found in table_schema_info.json",
                )

    def test_schema_strings_are_non_empty(self) -> None:
        for tbl, schema_str in TABLE_SCHEMAS.items():
            self.assertTrue(len(schema_str.strip()) > 0, f"TABLE_SCHEMAS['{tbl}'] is empty")


class TestSqlExamples(unittest.TestCase):
    def test_examples_exist_for_main_domains(self) -> None:
        required_domains = {"wip_realtime", "lot_history", "reject", "hold", "equipment"}
        for domain in required_domains:
            self.assertIn(domain, SQL_EXAMPLES, f"No SQL examples for domain '{domain}'")
            self.assertTrue(len(SQL_EXAMPLES[domain]) >= 2, f"Domain '{domain}' has fewer than 2 examples")

    def test_examples_are_select_statements(self) -> None:
        for domain, examples in SQL_EXAMPLES.items():
            for ex in examples:
                sql = ex.get("sql", "").strip().upper()
                self.assertTrue(
                    sql.startswith("SELECT"),
                    f"Example in domain '{domain}' does not start with SELECT: {sql[:60]}",
                )

    def test_examples_contain_fetch_first(self) -> None:
        for domain, examples in SQL_EXAMPLES.items():
            for ex in examples:
                sql = ex.get("sql", "").upper()
                self.assertIn(
                    "FETCH FIRST",
                    sql,
                    f"Example in domain '{domain}' missing FETCH FIRST: {sql[:60]}",
                )

    def test_examples_have_question_and_sql(self) -> None:
        for domain, examples in SQL_EXAMPLES.items():
            for i, ex in enumerate(examples):
                self.assertIn("question", ex, f"Domain '{domain}' example {i} missing 'question'")
                self.assertIn("sql", ex, f"Domain '{domain}' example {i} missing 'sql'")

    def test_examples_use_only_authorized_tables(self) -> None:
        # Build set of all short table names (without DWH.)
        authorized_short = {t.replace("DWH.", "") for t in _AUTHORIZED_TABLES}
        for domain, examples in SQL_EXAMPLES.items():
            for ex in examples:
                sql_upper = ex.get("sql", "").upper()
                # Find all FROM/JOIN DWH.* references
                refs = re.findall(r"FROM\s+DWH\.(\w+)|JOIN\s+DWH\.(\w+)", sql_upper)
                for ref_pair in refs:
                    tbl = next(r for r in ref_pair if r)
                    self.assertIn(
                        tbl, authorized_short,
                        f"Domain '{domain}' example references unauthorized table DWH.{tbl}",
                    )


class TestHelperFunctions(unittest.TestCase):
    def test_get_schemas_for_domains_returns_string(self) -> None:
        result = get_schemas_for_domains(["wip_realtime", "hold"])
        self.assertIsInstance(result, str)
        self.assertIn("DWH.DW_MES_LOT_V", result)
        self.assertIn("DWH.DW_MES_HOLDRELEASEHISTORY", result)

    def test_get_schemas_for_domains_no_duplicates(self) -> None:
        # When the same domain is passed twice, each unique table should appear only once.
        # Use an exact header pattern "### DWH.DW_MES_RESOURCE\n" to avoid matching
        # the substring in "DWH.DW_MES_RESOURCESTATUS" etc.
        result = get_schemas_for_domains(["equipment", "equipment"])
        self.assertEqual(result.count("### DWH.DW_MES_RESOURCE\n"), 1)

    def test_get_schemas_for_unknown_domain_returns_empty(self) -> None:
        result = get_schemas_for_domains(["nonexistent_domain"])
        self.assertEqual(result, "")

    def test_get_examples_for_domains_returns_string(self) -> None:
        result = get_examples_for_domains(["reject"])
        self.assertIsInstance(result, str)
        self.assertIn("SELECT", result.upper())

    def test_get_examples_for_unknown_domain_returns_empty(self) -> None:
        result = get_examples_for_domains(["nonexistent_domain"])
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
