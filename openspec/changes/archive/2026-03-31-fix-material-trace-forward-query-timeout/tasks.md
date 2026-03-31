## 1. Fix queue name in service and route

- [x] 1.1 Add `MATERIAL_TRACE_QUEUE = os.getenv("TRACE_WORKER_QUEUE", "trace-events")` constant in `src/mes_dashboard/services/material_trace_service.py`
- [x] 1.2 Import `MATERIAL_TRACE_QUEUE` in `src/mes_dashboard/routes/material_trace_routes.py` and replace hard-coded `queue_name="default"` with `queue_name=MATERIAL_TRACE_QUEUE`

## 2. Verification

- [x] 2.1 Restart server (`./scripts/start_server.sh stop && ./scripts/start_server.sh start`) and confirm RQ worker logs show the job being picked up for a forward query
- [x] 2.2 Execute a forward query on the material-trace page and verify results are returned without timeout
- [x] 2.3 Run existing tests (`pytest tests/ -k material_trace -v`) to confirm no regressions
