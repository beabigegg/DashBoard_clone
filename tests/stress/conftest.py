# -*- coding: utf-8 -*-
"""Pytest configuration for stress tests."""

import pytest
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


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
        if self.errors:
            lines.append(f"Errors (first 5):")
            for err in self.errors[:5]:
                lines.append(f"  - {err[:100]}")
        return "\n".join(lines)


@pytest.fixture(scope="session")
def base_url() -> str:
    """Get the base URL for stress testing."""
    return os.environ.get('STRESS_TEST_URL', 'http://127.0.0.1:5000')


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


def pytest_configure(config):
    """Add custom markers for stress tests."""
    config.addinivalue_line(
        "markers", "stress: mark test as stress test (may take longer)"
    )
    config.addinivalue_line(
        "markers", "load: mark test as load test (concurrent requests)"
    )
