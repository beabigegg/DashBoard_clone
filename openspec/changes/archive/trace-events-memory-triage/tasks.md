## 1. Admission Control (profile-aware)

- [x] 1.1 Add `TRACE_EVENTS_CID_LIMIT` env var (default 50000) to `trace_routes.py`
- [x] 1.2 Add CID count check in `events()` endpoint: for non-MSD profiles, if `len(container_ids) > TRACE_EVENTS_CID_LIMIT`, return HTTP 413 with `{ "code": "CID_LIMIT_EXCEEDED", "cid_count": N, "limit": M }`
- [x] 1.3 For MSD profile: bypass CID hard limit, log warning when CID count > 50000
- [x] 1.4 Add unit tests: non-MSD CID > limit → 413; MSD CID > limit → proceeds normally

## 2. Batch Fetch (fetchmany) in database.py

- [x] 2.1 Add `read_sql_df_slow_iter(sql, params, timeout_seconds, batch_size)` generator function to `database.py` that yields `(columns, rows)` tuples using `cursor.fetchmany(batch_size)`
- [x] 2.2 Add `DB_SLOW_FETCHMANY_SIZE` to `get_db_runtime_config()` (default 5000)
- [x] 2.3 Add unit test for `read_sql_df_slow_iter` (mock cursor, verify fetchmany calls and yields)

## 3. EventFetcher Memory Optimization

- [x] 3.1 Modify `_fetch_batch` in `event_fetcher.py` to use `read_sql_df_slow_iter` instead of `read_sql_df` — iterate rows directly, skip DataFrame, group to `grouped` dict immediately
- [x] 3.2 Update `_sanitize_record` to work with `dict(zip(columns, row))` instead of `row.to_dict()`
- [x] 3.3 Add unit test verifying EventFetcher uses `read_sql_df_slow_iter` import
- [x] 3.4 Update existing EventFetcher tests (mock `read_sql_df_slow_iter` instead of `read_sql_df`)

## 4. trace_routes Memory Optimization

- [x] 4.1 Modify events endpoint: only keep `raw_domain_results[domain]` for MSD profile; for non-MSD, `del events_by_cid` after flattening
- [x] 4.2 Verify existing `del raw_domain_results` and `gc.collect()` logic still correct after refactor

## 5. Deployment Configuration

- [x] 5.1 Update `.env.example`: add `TRACE_EVENTS_CID_LIMIT`, `DB_SLOW_FETCHMANY_SIZE` with descriptions
- [x] 5.2 Update `.env.example`: change `GUNICORN_WORKERS` default comment to recommend 2 for ≤ 8GB RAM
- [x] 5.3 Update `.env.example`: change `TRACE_EVENTS_MAX_WORKERS` and `EVENT_FETCHER_MAX_WORKERS` default to 2
- [x] 5.4 Update `deploy/mes-dashboard.service`: add `MemoryHigh=5G` and `MemoryMax=6G`
- [x] 5.5 Update `deploy/mes-dashboard.service`: add comment explaining memory limits

## 6. Verification

- [x] 6.1 Run `python -m pytest tests/ -v` — all existing tests pass (1069 passed, 152 skipped)
- [x] 6.2 Verify `.env.example` env var documentation is consistent with code defaults
