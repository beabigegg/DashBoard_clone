## ADDED Requirements

### Requirement: BatchQueryEngine SHALL provide time-range decomposition
The module SHALL decompose long date ranges into manageable monthly chunks to prevent Oracle timeout.

#### Scenario: Decompose date range into monthly chunks
- **WHEN** `decompose_by_time_range(start_date, end_date, grain_days=31)` is called
- **THEN** the date range SHALL be split into chunks of at most `grain_days` days each
- **THEN** each chunk SHALL contain `chunk_start` and `chunk_end` date strings
- **THEN** chunks SHALL be contiguous and non-overlapping, covering the full range

#### Scenario: Short date range returns single chunk
- **WHEN** the date range is shorter than or equal to `grain_days`
- **THEN** a single chunk covering the full range SHALL be returned

#### Scenario: Time-chunk boundary semantics are deterministic
- **WHEN** a date range is decomposed into multiple chunks
- **THEN** each chunk SHALL use a closed interval `[chunk_start, chunk_end]`
- **THEN** the next chunk SHALL start at `previous_chunk_end + 1 day`
- **THEN** the final chunk MAY contain fewer than `grain_days` days
- **THEN** chunk ranges SHALL have no overlap and no gap

### Requirement: BatchQueryEngine SHALL provide ID-batch decomposition
The module SHALL decompose large ID lists (from workorder/lot/GD lot/serial resolve expansion) into batches respecting Oracle IN-clause limits.

#### Scenario: Decompose ID list into batches
- **WHEN** `decompose_by_ids(ids, batch_size=1000)` is called with more than `batch_size` IDs
- **THEN** the ID list SHALL be split into batches of at most `batch_size` items each

#### Scenario: Small ID list returns single batch
- **WHEN** the ID list has fewer than or equal to `batch_size` items
- **THEN** a single batch containing all IDs SHALL be returned

### Requirement: BatchQueryEngine SHALL execute chunk plans with controlled parallelism
The module SHALL execute query chunks sequentially by default, with opt-in parallel execution respecting the slow query semaphore.

#### Scenario: Sequential execution (default)
- **WHEN** `execute_plan(chunks, query_fn, parallel=1)` is called
- **THEN** chunks SHALL be executed one at a time in order
- **THEN** each chunk result SHALL be stored to Redis immediately after completion
- **THEN** the function SHALL return a `query_hash` identifying the batch result

#### Scenario: Parallel execution with semaphore awareness
- **WHEN** `execute_plan(chunks, query_fn, parallel=2)` is called
- **THEN** up to `parallel` chunks SHALL execute concurrently via ThreadPoolExecutor
- **THEN** each thread SHALL acquire the slow query semaphore before executing `query_fn`
- **THEN** actual concurrency SHALL be capped at `min(parallel, available_semaphore_permits - 1)`
- **THEN** if semaphore is fully occupied, execution SHALL degrade to sequential

#### Scenario: All engine queries use dedicated connection
- **WHEN** a chunk's `query_fn` executes an Oracle query
- **THEN** it SHALL use `read_sql_df_slow` (dedicated connection, 300s timeout, semaphore-controlled)
- **THEN** pooled connection (`read_sql_df`) SHALL NOT be used for engine-managed queries

### Requirement: BatchQueryEngine SHALL enforce memory guards per chunk
The module SHALL check each chunk result's memory usage and abort if it exceeds a configurable threshold.

#### Scenario: Chunk memory within limit
- **WHEN** a chunk query returns a DataFrame within `BATCH_CHUNK_MAX_MEMORY_MB` (default 256MB, env-configurable)
- **THEN** the chunk SHALL be stored to Redis and marked as completed

#### Scenario: Chunk memory exceeds limit
- **WHEN** a chunk query returns a DataFrame exceeding `BATCH_CHUNK_MAX_MEMORY_MB`
- **THEN** the chunk SHALL be discarded (NOT stored to Redis)
- **THEN** the chunk SHALL be marked as failed in metadata with reason `memory_limit_exceeded`
- **THEN** a warning log SHALL include chunk index, actual memory MB, and threshold
- **THEN** remaining chunks SHALL continue execution

#### Scenario: Result row count limit
- **WHEN** `max_rows_per_chunk` is configured
- **THEN** the engine SHALL pass this limit to `query_fn` for SQL-level truncation (e.g., `FETCH FIRST N ROWS ONLY`)
- **THEN** if the result contains exactly `max_rows_per_chunk` rows, metadata SHALL include `truncated=True`

### Requirement: BatchQueryEngine SHALL support partial cache hits
The module SHALL check Redis for previously cached chunks and skip re-execution for cached chunks.

#### Scenario: Partial cache hit skips cached chunks
- **WHEN** `execute_plan(chunks, query_fn, skip_cached=True)` is called
- **THEN** for each chunk, Redis SHALL be checked for an existing cached result
- **THEN** chunks with valid cached results SHALL NOT be re-executed
- **THEN** only uncached chunks SHALL be passed to `query_fn`

#### Scenario: Full cache hit skips all execution
- **WHEN** all chunks already exist in Redis cache
- **THEN** no Oracle queries SHALL be executed
- **THEN** `merge_chunks()` SHALL return the combined cached DataFrames

### Requirement: BatchQueryEngine SHALL generate deterministic query_hash
The module SHALL use a stable hash for cache/progress keys so semantically identical queries map to the same batch identity.

#### Scenario: Stable hash for equivalent parameters
- **WHEN** two requests contain the same semantic query parameters in different input order
- **THEN** canonicalization SHALL normalize ordering before hashing
- **THEN** `query_hash` SHALL be identical for both requests

#### Scenario: Hash changes only when dataset-affecting parameters change
- **WHEN** parameters affecting the raw dataset (date range, mode, resolved IDs, core filters) change
- **THEN** `query_hash` SHALL change
- **THEN** presentation-only parameters SHALL NOT change `query_hash`

### Requirement: BatchQueryEngine SHALL define chunk-cache to service-cache handoff
The module SHALL integrate chunk-level cache with existing service-level dataset caches without breaking query_id-based view APIs.

#### Scenario: Chunk merge backfills service dataset cache
- **WHEN** chunk results are loaded/merged into a complete dataset for a primary query
- **THEN** the merged DataFrame SHALL be written back to the service's existing dataset cache layers (L1 process + L2 Redis)
- **THEN** downstream `/view` queries using the service `query_id` SHALL continue to work without additional Oracle queries

#### Scenario: Service cache miss with chunk cache hit
- **WHEN** a service-level dataset cache entry has expired but relevant chunk cache keys still exist
- **THEN** the engine SHALL rebuild the merged dataset from chunk cache
- **THEN** the service dataset cache SHALL be repopulated before returning response

### Requirement: BatchQueryEngine SHALL store chunk results in Redis
The module SHALL store each chunk as a separate Redis key using parquet-in-Redis format.

#### Scenario: Chunk storage key format
- **WHEN** a chunk result is stored
- **THEN** the Redis key SHALL follow the pattern `batch:{cache_prefix}:{query_hash}:chunk:{idx}`
- **THEN** each chunk SHALL be stored as a parquet-encoded base64 string via `redis_df_store`
- **THEN** each chunk key SHALL have a TTL matching the service's cache TTL (default 900 seconds)

#### Scenario: Chunk metadata tracking
- **WHEN** chunks are being executed
- **THEN** a metadata key `batch:{cache_prefix}:{query_hash}:meta` SHALL be updated via Redis HSET
- **THEN** metadata SHALL include `total`, `completed`, `failed`, `pct`, `status`, and `has_partial_failure` fields

### Requirement: BatchQueryEngine SHALL merge chunk results into a single DataFrame
The module SHALL provide result assembly from cached chunks.

#### Scenario: Merge all chunks
- **WHEN** `merge_chunks(query_hash)` is called
- **THEN** all chunk DataFrames SHALL be loaded from Redis and concatenated via `pd.concat`
- **THEN** if any chunk is missing, the merge SHALL proceed with available chunks and set `has_partial_failure=True`

#### Scenario: Iterate chunks for streaming
- **WHEN** `iterate_chunks(query_hash)` is called
- **THEN** chunk DataFrames SHALL be yielded one at a time without loading all into memory simultaneously

### Requirement: BatchQueryEngine SHALL handle chunk failures gracefully
The module SHALL continue execution when individual chunks fail and report partial results.

#### Scenario: Single chunk failure
- **WHEN** a chunk's `query_fn` raises an exception (timeout, ORA error, etc.)
- **THEN** the error SHALL be logged with chunk index and exception details
- **THEN** the failed chunk SHALL be marked as failed in metadata
- **THEN** remaining chunks SHALL continue execution

#### Scenario: All chunks fail
- **WHEN** all chunks' `query_fn` calls raise exceptions
- **THEN** metadata status SHALL be set to `failed`
- **THEN** `merge_chunks()` SHALL return an empty DataFrame

### Requirement: Shared redis_df_store module SHALL provide parquet-in-Redis utilities
The module SHALL provide reusable DataFrame serialization to/from Redis using parquet + base64 encoding.

#### Scenario: Store DataFrame to Redis
- **WHEN** `redis_store_df(key, df, ttl)` is called
- **THEN** the DataFrame SHALL be serialized to parquet format using pyarrow
- **THEN** the parquet bytes SHALL be base64-encoded and stored via Redis SETEX with the given TTL
- **THEN** if Redis is unavailable, the function SHALL log a warning and return without error

#### Scenario: Load DataFrame from Redis
- **WHEN** `redis_load_df(key)` is called
- **THEN** the base64 string SHALL be loaded from Redis, decoded, and deserialized to a DataFrame
- **THEN** if the key does not exist or Redis is unavailable, the function SHALL return None
