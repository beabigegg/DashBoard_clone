## 1. EventFetcher Streaming Core

- [x] 1.1 新增 `EventFetcher._stream_batches_to_writer(normalized_ids, domain, row_callback)` — 提取現有 batch/threading/jobs CONTAINERIDS 展開邏輯，改以 callback 輸出 `(columns, rows)`；無 row guard；返回 `(total_row_count, failures)`
- [x] 1.2 改寫 `fetch_events_to_parquet(container_ids, domain, dest_path)` — 呼叫 `_stream_batches_to_writer` + `pyarrow.ParquetWriter` 逐批寫入；返回值改為 `Tuple[int, Dict[str, Any]]`（row_count, quality_meta）；無資料時寫空 parquet
- [x] 1.3 在 `tests/test_event_fetcher.py` 新增測試：streaming 路徑超過 500k rows 不截斷、jobs domain CONTAINERIDS 展開正確、返回 `(int, dict)` tuple、partial failure 時 quality_meta.status = "partial"

## 2. MSD Compat Job Streaming

- [x] 2.1 在 `trace_job_service.py` 新增 `_write_msd_events_spool_from_paths(trace_query_id, domain_parquet_paths)` — 以 `pq.ParquetFile.iter_batches()` streaming 合併多 domain parquet，呼叫 `register_stage_spool_file()`
- [x] 2.2 改寫 `mid_section_defect_service._execute_msd_compat_job()` event fetch loop（line ~1044）— 替換 `fetch_events()` in-memory loop 為 `fetch_events_to_parquet()` per domain + `_write_msd_events_spool_from_paths()`；用 `tempfile.mkdtemp` 管理 tmp parquet，`finally` 中 `shutil.rmtree` 清理

## 3. Trace Job MSD Branch Streaming

- [x] 3.1 在 `_build_job_msd_aggregation()` 新增 DuckDB spool hit 路徑 — 若 `trace_query_id` 有效且 `MsdDuckdbRuntime(trace_query_id).is_available()`，呼叫 `get_summary()` 並注入 `domain_quality_meta`，返回 summary；失敗時 fallback 至原有 in-memory 路徑
- [x] 3.2 改寫 `_execute_trace_events_job()` 中 `is_msd=True` 的 event fetch 分支 — 改用 `fetch_events_to_parquet()` per domain 收集 `quality_meta`；呼叫 `_write_msd_events_spool_from_paths()` 寫 spool；`raw_domain_results` 改為 `{}`（aggregation 由 DuckDB spool 提供）；非 MSD 路徑不動

## 4. Material Trace Streaming

- [x] 4.1 在 `material_trace_service.py` 新增 `_execute_batched_query_to_parquet(sql_name, column, values, dest_path, wc_names, *, allow_patterns, mapping)` — 使用 `read_sql_df_slow_iter` 逐批迭代 + `pyarrow.ParquetWriter`；每 chunk inline map `WORKCENTER_GROUP`；不呼叫 `_check_memory_guard()`；無資料時寫空 parquet；返回 row_count
- [x] 4.2 改寫 `material_trace_service.execute_to_spool()` — 替換 `_execute_batched_query() → _check_memory_guard() → df.to_parquet()` 為 `_execute_batched_query_to_parquet() → register_spool_file()`；`_check_memory_guard()` 不再被呼叫於 spool 路徑

## 5. Tests & Verification

- [x] 5.1 在 `tests/test_material_trace_service.py` 新增或更新測試：`execute_to_spool()` streaming 路徑不呼叫 `_check_memory_guard`
- [x] 5.2 執行 `pytest tests/test_event_fetcher.py tests/test_material_trace_service.py -v` 確認所有測試通過
- [ ] 5.3 end-to-end 驗證：執行 MSD 查詢（大範圍日期），確認不再出現「事件資料已截斷」警告；server log 中 `EventFetcher.fetch_events_to_parquet` rows 不受 500k 限制
- [ ] 5.4 end-to-end 驗證：執行追溯工具大範圍查詢，確認不因 256 MB guard 失敗
