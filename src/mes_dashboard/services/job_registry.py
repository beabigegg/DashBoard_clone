# -*- coding: utf-8 -*-
"""Central async-job registry for RQ job types.

Declares all known job types in one place so they can be dispatched by
job_type string without hard-coded conditionals at the call site.

Usage (in each job service, appended after all definitions):

    from mes_dashboard.services.job_registry import JobTypeConfig, register_job_type

    register_job_type(JobTypeConfig(
        job_type="reject",
        queue_name="reject-query",
        worker_fn=execute_reject_query_job,
    ))

Consumers query the registry via get_job_type_config() or list_registered_job_types().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class JobTypeConfig:
    """Configuration record for a single registered async job type."""

    job_type: str
    """Global unique identifier for this job type; also used as Redis prefix."""

    queue_name: str
    """RQ queue name to submit jobs into."""

    worker_fn: Callable
    """Reference to the worker entry-point function (execute_xxx_job)."""

    timeout_seconds: int = 1800
    """RQ job_timeout — worker is killed after this many seconds."""

    ttl_seconds: int = 3600
    """RQ result_ttl and failure_ttl — how long metadata persists in Redis."""

    should_enqueue: Optional[Callable[[Dict[str, Any]], bool]] = None
    """Optional guard: called with params dict; job is skipped when it returns False."""


# ---------------------------------------------------------------------------
# Private registry store
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, JobTypeConfig] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_job_type(config: JobTypeConfig) -> None:
    """Register a job type configuration.

    Idempotent: registering the same job_type twice overwrites the prior entry.
    Module-level side-effect — called once per job service at import time.
    """
    _REGISTRY[config.job_type] = config


def get_job_type_config(job_type: str) -> Optional[JobTypeConfig]:
    """Return the JobTypeConfig for *job_type*, or None if not registered.

    Never raises — callers are expected to handle the None case.
    """
    return _REGISTRY.get(job_type)


def list_registered_job_types() -> List[str]:
    """Return a list of all registered job_type strings."""
    return list(_REGISTRY.keys())
