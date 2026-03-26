## 1. Backend — Expose package field in API payload

- [x] 1.1 In `src/mes_dashboard/services/qc_gate_service.py`, add `'package': _safe_value(row.get('PACKAGE_LEF'))` to the dict returned by `_build_lot_payload()`

## 2. Frontend — Add Package column to LOT detail table

- [x] 2.1 In `frontend/src/qc-gate/components/LotTable.vue`, insert `{ key: 'package', label: 'Package' }` into the `HEADERS` array at index 1 (after LOT ID)
- [x] 2.2 In the `<tbody>` template, add `<td>{{ formatValue(lot.package) }}</td>` after the `lot_id` cell

## 3. Verification

- [x] 3.1 Run existing backend tests to confirm no regressions
- [x] 3.2 Run existing frontend tests/lint to confirm no regressions
