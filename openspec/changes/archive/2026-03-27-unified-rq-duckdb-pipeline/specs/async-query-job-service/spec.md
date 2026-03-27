## MODIFIED Requirements

### Requirement: Async job service SHALL support multi-stage progress reporting
The shared async query job service SHALL support reporting progress across multiple pipeline stages within a single job.

#### Scenario: Multi-stage progress update
- **WHEN** an RQ job has multiple stages (e.g., seed_detection, lineage, events, aggregation)
- **THEN** `update_job_progress()` SHALL accept a `stage` parameter
- **THEN** the progress metadata in Redis SHALL include `{ "status": "running", "stage": "lineage", "progress": "60%", "completed_stages": ["seed_detection"] }`

#### Scenario: Frontend reads stage progress
- **WHEN** `GET /api/trace/job/<job_id>` is called for a multi-stage job
- **THEN** the response SHALL include `stage` and `completed_stages` fields
- **THEN** the frontend SHALL display the current stage name and overall progress

### Requirement: Async job service SHALL support warmup job enqueueing
The async job service SHALL support enqueueing warmup jobs with lower priority than user-initiated queries.

#### Scenario: Warmup job enqueue
- **WHEN** the warmup scheduler enqueues a warmup job
- **THEN** the job SHALL be enqueued to the designated queue
- **THEN** user-initiated query jobs on the same queue SHALL execute before warmup jobs when both are pending
