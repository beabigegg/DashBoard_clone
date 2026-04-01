# -*- coding: utf-8 -*-
"""Session-level result registries for stress test terminal summaries.

These lists are populated during test execution and consumed by
pytest_terminal_summary in conftest.py. They live here so that test
modules can import them without importing from conftest (which would
resolve to the top-level tests/conftest.py under pytest's module
loading rules).
"""

from typing import List

# Registry for load summaries collected during the session.
# Each entry is (test_name: str, LoadSummary).
session_load_summaries: List[tuple] = []

# Registry for chunk boundary probe results.
# Each entry is (label: str, status: str, detail: str).
session_chunk_boundary_results: List[tuple] = []

# Registry for data integrity results.
# Each entry is (service_name: str, IntegrityResult).
session_integrity_results: List[tuple] = []


def record_load_summary(test_name: str, summary) -> None:
    """Register a LoadSummary for the terminal report."""
    if summary is not None:
        session_load_summaries.append((test_name, summary))


def record_chunk_boundary(label: str, status: str, detail: str = "") -> None:
    """Register a chunk boundary probe result."""
    session_chunk_boundary_results.append((label, status, detail))


def record_integrity_result(service: str, result) -> None:
    """Register a per-service integrity result."""
    session_integrity_results.append((service, result))
