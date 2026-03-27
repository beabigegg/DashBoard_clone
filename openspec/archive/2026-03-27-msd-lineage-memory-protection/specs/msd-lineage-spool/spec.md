## ADDED Requirements

### Requirement: MSD lineage stage SHALL support async execution via RQ for large seed sets
The `trace_routes.py /lineage` endpoint SHALL detect when MSD profile seed count exceeds `LINEAGE_SEED_ASYNC_THRESHOLD` and enqueue lineage resolution to a background RQ worker.

#### Scenario: Seed count exceeds async threshold
- **WHEN** `POST /api/trace/lineage` is called with `profile=mid_section_defect` and `len(container_ids) > LINEAGE_SEED_ASYNC_THRESHOLD` (default 5000)
- **THEN** the endpoint SHALL enqueue a lineage resolution job to the `msd-analysis` RQ queue
- **THEN** the endpoint SHALL return HTTP 202 with `{"async": true, "job_id": "<id>", "status_url": "/api/trace/lineage/job/<job_id>"}`

#### Scenario: Seed count within sync threshold
- **WHEN** `POST /api/trace/lineage` is called with `profile=mid_section_defect` and `len(container_ids) <= LINEAGE_SEED_ASYNC_THRESHOLD`
- **THEN** the endpoint SHALL execute lineage resolution synchronously (existing behavior)

#### Scenario: Async unavailable fallback
- **WHEN** seed count exceeds threshold but `is_async_available()` returns False
- **THEN** the endpoint SHALL attempt sync execution with RSS guard check
- **THEN** if RSS guard rejects, the endpoint SHALL return HTTP 503 with retry hint

#### Scenario: Non-MSD profiles unaffected
- **WHEN** `POST /api/trace/lineage` is called with `profile=query_tool` regardless of seed count
- **THEN** the endpoint SHALL execute synchronously (existing behavior unchanged)

### Requirement: MSD lineage RQ job SHALL spool results to parquet
The MSD lineage async job SHALL execute lineage resolution in batches and spool the graph result to a parquet file via `query_spool_store`.

#### Scenario: Batched split ancestor resolution
- **WHEN** the RQ worker executes a lineage job with N seed CIDs
- **THEN** it SHALL decompose seeds into batches of `ORACLE_IN_BATCH_SIZE` (1000)
- **THEN** it SHALL call `LineageEngine.resolve_split_ancestors()` per batch
- **THEN** it SHALL accumulate `child_to_parent` and `cid_to_name` across batches without holding all batch results simultaneously

#### Scenario: Merge source resolution after split completion
- **WHEN** all split ancestor batches are complete
- **THEN** the job SHALL collect all unique ancestor CIDs from the accumulated graph
- **THEN** the job SHALL call `LineageEngine.resolve_merge_sources()` with the full ancestor set
- **THEN** the job SHALL build the complete `ancestors` mapping per seed

#### Scenario: Graph result serialized to parquet spool
- **WHEN** lineage resolution is complete
- **THEN** the job SHALL serialize the graph as an edge-list DataFrame with columns: `seed_cid`, `ancestor_cid`, `edge_type` (split/merge), `cid_name`
- **THEN** the job SHALL store the parquet via `store_spooled_df()` with namespace `msd-lineage`
- **THEN** the job SHALL register the spool metadata in Redis for retrieval by subsequent pipeline stages

#### Scenario: Progress tracking during execution
- **WHEN** the lineage job is running
- **THEN** the job SHALL update Redis job progress after each batch completes
- **THEN** the progress SHALL include `completed_batches/total_batches` and percentage

### Requirement: Lineage job status and result endpoints SHALL be provided
The trace routes SHALL expose job status polling and result retrieval for async lineage jobs.

#### Scenario: Job status polling
- **WHEN** `GET /api/trace/lineage/job/<job_id>` is called
- **THEN** it SHALL return `{"status": "<status>", "progress": "<progress>", "elapsed_seconds": N}`

#### Scenario: Job result retrieval
- **WHEN** `GET /api/trace/lineage/job/<job_id>/result` is called and job status is `completed`
- **THEN** it SHALL load the lineage graph from parquet spool and reconstruct the response format expected by `useTraceProgress` (ancestors, cid_to_name, parent_map, edges, nodes)

#### Scenario: Job expired
- **WHEN** `GET /api/trace/lineage/job/<job_id>` is called and no metadata exists in Redis
- **THEN** it SHALL return HTTP 404

### Requirement: Frontend useTraceProgress SHALL handle async lineage stage
The `useTraceProgress` composable SHALL detect HTTP 202 from the lineage stage and poll for completion.

#### Scenario: Async lineage response handling
- **WHEN** the lineage POST returns HTTP 202 with `{async: true, job_id, status_url}`
- **THEN** `useTraceProgress` SHALL poll `status_url` using `pollJobUntilComplete`
- **THEN** on completion it SHALL fetch the result and continue to events stage
- **THEN** `job_progress` reactive state SHALL reflect lineage job progress
