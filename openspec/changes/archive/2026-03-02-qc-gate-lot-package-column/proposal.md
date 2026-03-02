## Why

The QC-GATE LOT detail table currently lacks a dedicated Package column. The `PACKAGE_LEF` field from `DW_MES_LOT_V` is only used as a fallback for the Product column, making it invisible when Product has a value. Users need to see the package (lead-frame) information alongside the LOT ID to quickly identify packaging context during QC-GATE monitoring.

## What Changes

- Add a new **Package** column to the QC-GATE LOT detail table, positioned immediately after the LOT ID column.
- Expose the `PACKAGE_LEF` field from the WIP cache as a dedicated `package` field in the API response payload.
- No existing columns are removed or reordered beyond the insertion point.

## Capabilities

### New Capabilities
_(none — this is a column addition to an existing capability)_

### Modified Capabilities
- `qc-gate-status`: Add `package` field to LOT payload and display it as a new column after LOT ID in the detail table.

## Impact

- **Backend**: `qc_gate_service.py` — `_build_lot_payload()` adds a `package` key.
- **Frontend**: `LotTable.vue` — `HEADERS` array gains a new entry; template adds a `<td>` cell.
- **API**: `/api/qc-gate/summary` response shape gains `package` in each lot object (additive, non-breaking).
- **No DB changes**: `PACKAGE_LEF` already exists in `DW_MES_LOT_V` and is present in the Redis WIP cache.
