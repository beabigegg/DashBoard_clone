## Context

The QC-GATE LOT detail table (`LotTable.vue`) displays 9 columns sourced from the `/api/qc-gate/summary` API. The backend (`qc_gate_service.py`) builds each lot payload from the Redis-cached WIP snapshot of `DW_MES_LOT_V`. The `PACKAGE_LEF` column already exists in the WIP data but is currently only used as a fallback for the `product` field — it is never exposed independently.

## Goals / Non-Goals

**Goals:**
- Expose `PACKAGE_LEF` as a dedicated `package` field in each lot's API payload.
- Display a "Package" column in the LOT detail table, positioned immediately after "LOT ID".
- Keep the column sortable, consistent with existing column behavior.

**Non-Goals:**
- Changing the Product column's fallback logic (it still falls through to `PACKAGE_LEF` when `PRODUCT` is null).
- Adding chart-level grouping or filtering by package.
- Modifying the DB view or Redis cache schema — `PACKAGE_LEF` is already available.

## Decisions

1. **Field name: `package`** — Maps directly to `PACKAGE_LEF` from `DW_MES_LOT_V`. Simple, descriptive, consistent with existing snake_case payload keys (`lot_id`, `wait_hours`).

2. **Column position: after LOT ID (index 1)** — The user explicitly requested "放在LOT ID之後". Insert into `HEADERS` array at index 1, shifting Product and subsequent columns right.

3. **No backend query changes** — `PACKAGE_LEF` is already present in the WIP cache DataFrame. We just read it in `_build_lot_payload()`, same as other fields.

## Risks / Trade-offs

- **Wide table on small screens** → The table already has horizontal scroll (`lot-table-scroll`); adding one more column is acceptable.
- **Null values** → Many lots may have `PACKAGE_LEF = NULL`. The existing `formatValue()` helper already renders `'-'` for nulls, so no special handling needed.
