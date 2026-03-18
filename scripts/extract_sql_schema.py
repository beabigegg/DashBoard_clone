#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Development tool: scan sql/**/*.sql, extract column usage per table,
cross-reference with data/table_schema_info.json, and print frequency-ranked
column list per table.

Usage:
    python scripts/extract_sql_schema.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "src" / "mes_dashboard" / "sql"
SCHEMA_FILE = ROOT / "data" / "table_schema_info.json"


def main() -> None:
    schema_info = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

    # Build per-table column index: short_name -> {col_name -> data_type}
    table_cols: dict[str, dict[str, str]] = {}
    for tbl, info in schema_info.items():
        cols: dict[str, str] = {}
        for col_def in info.get("schema", []):
            cols[col_def["column_name"]] = col_def["data_type"]
        table_cols[tbl] = cols

    sql_files = list(SQL_DIR.rglob("*.sql"))
    print(f"Found {len(sql_files)} SQL files under {SQL_DIR}")

    # Count column occurrences per table
    col_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for f in sql_files:
        content = f.read_text(errors="replace").upper()
        for tbl, cols in table_cols.items():
            tbl_upper = tbl.upper()
            if tbl_upper not in content and f"DWH.{tbl_upper}" not in content:
                continue
            for col in cols:
                if re.search(r"\b" + re.escape(col) + r"\b", content):
                    col_usage[tbl][col] += 1

    print()
    for tbl in sorted(col_usage.keys()):
        cols_sorted = sorted(col_usage[tbl].items(), key=lambda x: x[1], reverse=True)
        print(f"=== {tbl} ({len(cols_sorted)} columns used) ===")
        for col, cnt in cols_sorted:
            dtype = table_cols[tbl].get(col, "?")
            print(f"  {col:40s} ({dtype:12s}) : {cnt}")
        print()

    # Also report tables with zero SQL usage
    unused = set(table_cols.keys()) - set(col_usage.keys())
    if unused:
        print(f"=== Tables with no SQL template usage ({len(unused)}) ===")
        for tbl in sorted(unused):
            print(f"  {tbl}")


if __name__ == "__main__":
    main()
