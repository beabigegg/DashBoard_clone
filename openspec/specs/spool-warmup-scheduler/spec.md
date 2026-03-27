# spool-warmup-scheduler Specification

## Purpose
Define scheduler-driven spool warmup ownership, eligibility, and leader-lock behavior.

## Requirements
### Requirement: Warmup scheduler SHALL only warm reports with a canonical warmup key
The spool warmup scheduler SHALL preload only those report datasets whose canonical warmup identity has been explicitly defined.

#### Scenario: Canonical report eligible for warmup
- **WHEN** a report has a stable canonical warmup key (for example reject, yield-alert, or hold date-range dataset)
- **THEN** the scheduler MAY preload its most recent data range into spool

#### Scenario: Report not yet canonicalized
- **WHEN** a report's query identity still depends on user-specific filters or unresolved variants
- **THEN** the scheduler SHALL NOT preload that report until the canonical warmup key design is completed

### Requirement: Warmup scheduler SHALL use leader locking
The scheduler SHALL prevent duplicate enqueue by multiple gunicorn workers.

#### Scenario: Multiple gunicorn workers boot simultaneously
- **WHEN** app initialization runs in more than one worker
- **THEN** only one worker SHALL acquire the warmup enqueue lock
- **THEN** only one warmup job SHALL be enqueued for that cycle

### Requirement: Warmup scheduler SHALL replace cache_updater dataset warmups
Reject/yield/hold-style dataset warmups SHALL move out of `cache_updater` and into the RQ-based warmup scheduler once the scheduler is active.

#### Scenario: Scheduler active
- **WHEN** the warmup scheduler is enabled
- **THEN** `cache_updater` SHALL stop running dataset warmups that belong to the spool pipeline
- **THEN** `cache_updater` SHALL continue to refresh non-spool caches

### Requirement: Warmup coverage SHALL expand selectively after canonicalization
Resource-history MAY be added to warmup after its canonical base dataset is implemented, but production-history SHALL remain excluded from scheduler-driven warmup in this change.

#### Scenario: Resource-history added later in the same change
- **WHEN** canonical warmup identity is defined for resource-history
- **THEN** the scheduler MAY include it in the warmup sequence

#### Scenario: Production-history remains excluded
- **WHEN** the scheduler evaluates warmup candidates in this change
- **THEN** it SHALL NOT enqueue production-history startup warmup
- **THEN** it SHALL NOT enqueue production-history periodic refresh jobs
