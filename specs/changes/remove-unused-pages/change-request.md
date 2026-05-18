# Change Request

## Original Request

移除專案中未使用的前端頁面：`tables`（使用者確認可移除）、`admin-performance`（孤立/廢棄）、`admin-user-usage-kpi`（孤立/廢棄）；並修補 `production-history` 未納入 vite build config 的問題。

## Business / User Goal

減少 codebase 死碼，降低維護負擔；確保 production-history 頁面正確打包進生產版本。

## Non-goals

- 不新增任何功能
- 不修改保留頁面的行為
- 不移除 Flask deprecated redirect（可選，列入範圍但不強制）

## Constraints

- 移除 `tables` 需清除 vite config、portal router、contracts、Flask routes 所有接線
- `admin-performance`、`admin-user-usage-kpi` 的 Flask deprecated redirect 是 admin_routes.py 中的重定向，移除時需確認不影響其他路由

## Known Context

Pre-audit findings（由 Explore agent 確認）：
- `admin-performance`：vite ❌、router ❌、contracts ❌、Flask = deprecated redirect → /admin/dashboard
- `admin-user-usage-kpi`：vite ❌、router ❌、contracts ❌、Flask = deprecated redirect → /admin/dashboard
- `tables`：vite ✅、router ✅、contracts ✅、Flask ✅（需完整清除）
- `production-history`：router ✅、contracts ✅、Flask ✅、vite ❌（missing from rollupOptions.input）

## Open Questions

（無）

## Requested Delivery Date / Priority

Low urgency — code cleanup
