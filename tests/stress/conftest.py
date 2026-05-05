# -*- coding: utf-8 -*-
"""Pytest configuration for stress tests."""

import pytest
import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Add src and stress test dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.dirname(__file__))

from load_collector import LoadCollector, LoadSummary, RQ_QUEUES
from stress_registry import (
    session_load_summaries,
    session_chunk_boundary_results,
    session_integrity_results,
)


@dataclass
class StressTestResult:
    """Container for stress test results."""
    test_name: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    response_times: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    load_summary: Optional[LoadSummary] = None

    @property
    def avg_response_time(self) -> float:
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100

    @property
    def requests_per_second(self) -> float:
        if self.total_duration == 0:
            return 0.0
        return self.total_requests / self.total_duration

    def add_success(self, response_time: float):
        self.total_requests += 1
        self.successful_requests += 1
        self.response_times.append(response_time)
        self.min_response_time = min(self.min_response_time, response_time)
        self.max_response_time = max(self.max_response_time, response_time)

    def add_failure(self, error: str, response_time: float = 0):
        self.total_requests += 1
        self.failed_requests += 1
        self.errors.append(error)
        if response_time > 0:
            self.response_times.append(response_time)

    def report(self) -> str:
        """Generate human-readable report."""
        lines = [
            f"\n{'='*60}",
            f"Stress Test Report: {self.test_name}",
            f"{'='*60}",
            f"Total Requests:      {self.total_requests}",
            f"Successful:          {self.successful_requests}",
            f"Failed:              {self.failed_requests}",
            f"Success Rate:        {self.success_rate:.2f}%",
            f"{'─'*60}",
            f"Total Duration:      {self.total_duration:.2f}s",
            f"Requests/Second:     {self.requests_per_second:.2f}",
            f"{'─'*60}",
            f"Min Response Time:   {self.min_response_time*1000:.2f}ms" if self.min_response_time != float('inf') else "Min Response Time:   N/A",
            f"Max Response Time:   {self.max_response_time*1000:.2f}ms",
            f"Avg Response Time:   {self.avg_response_time*1000:.2f}ms",
            f"{'='*60}",
        ]
        if self.load_summary is not None:
            ls = self.load_summary
            lines.append(f"{'─'*60}")
            lines.append("System Load Summary:")
            lines.append(f"  Samples:             {ls.sample_count} valid / {ls.null_sample_count} null")
            lines.append(f"  Duration:            {ls.duration_sec:.1f}s")
            if ls.peak_cpu_pct is not None:
                lines.append(f"  Peak CPU:            {ls.peak_cpu_pct:.1f}%")
            if ls.avg_cpu_pct is not None:
                lines.append(f"  Avg CPU:             {ls.avg_cpu_pct:.1f}%")
            if ls.peak_mem_pct is not None:
                lines.append(f"  Peak Memory:         {ls.peak_mem_pct:.1f}%")
            if ls.avg_mem_pct is not None:
                lines.append(f"  Avg Memory:          {ls.avg_mem_pct:.1f}%")
            if ls.peak_db_pool_pct is not None:
                lines.append(f"  Peak DB Pool:        {ls.peak_db_pool_pct:.1f}%")
            else:
                lines.append("  Peak DB Pool:        N/A")
            if ls.peak_queue_depths:
                lines.append("  Peak RQ Queue Depths:")
                for q in RQ_QUEUES:
                    depth = ls.peak_queue_depths.get(q, 0)
                    lines.append(f"    {q:<32} {depth}")
            if ls.telemetry_diff is not None:
                td = ls.telemetry_diff
                lines.append(f"{'─'*60}")
                lines.append("Telemetry Diff (during test):")
                if td.endpoint_unavailable:
                    lines.append("  (admin endpoint unavailable — counters not captured)")
                elif td.all_zero:
                    lines.append("  No guard/spillover events detected")
                else:
                    lines.append(f"  Guard Rejections:    {td.guard_reject_total}")
                    lines.append(f"  Async Fallbacks:     {td.async_fallback_total}")
                    lines.append(f"  Memory Errors:       {td.memory_error_total}")
                    lines.append(f"  Spool Cache Hits:    {td.spool_cache_hit}")
                    lines.append(f"  Spool Cache Misses:  {td.spool_cache_miss}")
        if self.errors:
            lines.append("Errors (first 5):")
            for err in self.errors[:5]:
                lines.append(f"  - {err[:100]}")
        return "\n".join(lines)


@pytest.fixture(scope="session")
def base_url() -> str:
    """Get the base URL for stress testing."""
    return os.environ.get('STRESS_TEST_URL', 'http://127.0.0.1:8080')


@pytest.fixture(scope="session")
def stress_config() -> Dict[str, Any]:
    """Get stress test configuration."""
    return {
        'concurrent_users': int(os.environ.get('STRESS_CONCURRENT_USERS', '10')),
        'requests_per_user': int(os.environ.get('STRESS_REQUESTS_PER_USER', '20')),
        'ramp_up_time': float(os.environ.get('STRESS_RAMP_UP_TIME', '2.0')),
        'timeout': float(os.environ.get('STRESS_TIMEOUT', '30.0')),
    }


@pytest.fixture
def stress_result():
    """Factory fixture to create stress test results."""
    def _create_result(test_name: str) -> StressTestResult:
        return StressTestResult(test_name=test_name)
    return _create_result


@pytest.fixture(scope="session")
def load_collector_factory(base_url) -> callable:
    """Session-scoped factory that creates LoadCollector instances."""
    def _factory(url: Optional[str] = None, interval: float = 2.0) -> LoadCollector:
        return LoadCollector(url or base_url, interval=interval)
    return _factory


@pytest.fixture
def load_collector(base_url) -> LoadCollector:
    """Function-scoped LoadCollector pre-configured from env/config."""
    interval = float(os.environ.get("STRESS_LOAD_INTERVAL", "2.0"))
    return LoadCollector(base_url, interval=interval)




def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Emit consolidated load monitoring / boundary / integrity tables at session end."""
    if session_load_summaries:
        terminalreporter.write_sep("=", "Load Monitoring Summary")
        header = f"{'Test':<50} {'CPU pk':>7} {'CPU av':>7} {'Mem pk':>7} {'Mem av':>7} {'DBPool':>7} {'Samples':>8}"
        terminalreporter.write_line(header)
        terminalreporter.write_line("-" * len(header))
        for test_name, ls in session_load_summaries:
            cpu_pk = f"{ls.peak_cpu_pct:.1f}%" if ls.peak_cpu_pct is not None else "N/A"
            cpu_av = f"{ls.avg_cpu_pct:.1f}%" if ls.avg_cpu_pct is not None else "N/A"
            mem_pk = f"{ls.peak_mem_pct:.1f}%" if ls.peak_mem_pct is not None else "N/A"
            mem_av = f"{ls.avg_mem_pct:.1f}%" if ls.avg_mem_pct is not None else "N/A"
            pool = f"{ls.peak_db_pool_pct:.1f}%" if ls.peak_db_pool_pct is not None else "N/A"
            samples = f"{ls.sample_count}v/{ls.null_sample_count}n"
            row = f"{test_name[:50]:<50} {cpu_pk:>7} {cpu_av:>7} {mem_pk:>7} {mem_av:>7} {pool:>7} {samples:>8}"
            terminalreporter.write_line(row)

    if session_chunk_boundary_results:
        terminalreporter.write_sep("=", "Chunk Boundary Probe Summary")
        for label, status, detail in session_chunk_boundary_results:
            marker = "OK" if status == "OK" else "UNEXPECTED"
            suffix = f" — {detail}" if detail else ""
            terminalreporter.write_line(f"  [{marker:>10}]  {label}{suffix}")

    if session_integrity_results:
        terminalreporter.write_sep("=", "Data Integrity Summary")
        header = f"{'Service':<35} {'Verdict':<12} {'Baseline':>10} {'API rows':>10} {'Deficit':>8}"
        terminalreporter.write_line(header)
        terminalreporter.write_line("-" * len(header))
        for service, ir in session_integrity_results:
            verdict = getattr(ir, "verdict", "SKIPPED")
            baseline = str(getattr(ir, "baseline_count", "N/A"))
            api_rows = str(getattr(ir, "api_total_rows", "N/A"))
            deficit = f"{getattr(ir, 'deficit_pct', 0.0):.2f}%" if getattr(ir, "deficit_pct", None) is not None else "N/A"
            row = f"{service:<35} {verdict:<12} {baseline:>10} {api_rows:>10} {deficit:>8}"
            terminalreporter.write_line(row)


def pytest_configure(config):
    """Add custom markers for stress tests."""
    config.addinivalue_line(
        "markers", "stress: mark test as stress test (may take longer)"
    )
    config.addinivalue_line(
        "markers", "load: mark test as load test (concurrent requests)"
    )
