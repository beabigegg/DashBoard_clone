# MES Dashboard - Claude Code Instructions

## Project Overview
MES Dashboard 是一個工廠製造執行系統的儀表板應用，使用 Flask + Oracle 資料庫 + ECharts 前端圖表。

## Before Starting Any Task
1. **Review architecture documentation**: Read `docs/architecture_findings.md` to understand:
   - Database connection management patterns
   - Caching mechanisms and TTL constants
   - Filter cache (workcenter/family) usage
   - Frontend global components (Toast, MesApi)
   - Data table filtering rules and column mappings
   - E10 status definitions and OU% calculation
   - Testing conventions

## When Making Changes
If any of the following patterns are modified or new patterns are discovered:
- Database connection or pooling approach
- Caching strategy or TTL values
- Global frontend components usage
- Data table column names or filtering rules
- New shared utilities or services
- Testing conventions or setup patterns

**Update `docs/architecture_findings.md`** to reflect the changes.

## Key Architecture Rules

### Database
- Always use `mes_dashboard.core.database.read_sql_df()` for queries
- Never create direct connections in services
- Reset `db._ENGINE = None` in test setUp

### Caching
- Use `mes_dashboard.core.cache` for all caching operations
- Use `mes_dashboard.services.filter_cache` for workcenter/family lookups
- Always convert WORKCENTERNAME → WORKCENTER_GROUP for display

### Frontend
- Toast notifications: Use `Toast.warning()`, `Toast.error()`, `Toast.success()` (NOT MESToast)
- API calls: Use `MesApi.get()` with proper timeout
- Array operations: Remember `.reverse()` modifies in-place

### Data Tables
- DW_MES_RESOURCE: Use `PJ_ASSETSSTATUS` (not ASSETSTATUS), `LOCATIONNAME` (not LOCATION)
- DW_MES_RESOURCESTATUS_SHIFT: HISTORYID maps to RESOURCEID
- DW_PJ_LOT_V: Source for WORKCENTER_GROUP mapping

### SQL
- Use `/*+ MATERIALIZE */` hint for Oracle CTEs used multiple times
- Date range: `TXNDATE >= start AND TXNDATE < end + 1`
- Apply EQUIPMENT_TYPE_FILTER, location exclusions, asset status exclusions

## Testing
- Unit tests: `tests/test_*_service.py`
- Integration tests: `tests/test_*_routes.py`
- E2E tests: `tests/e2e/test_*_e2e.py`
- For parallel queries (ThreadPoolExecutor), mock with function-based side_effect, not list
