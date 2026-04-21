"""Hypothesis profile configuration for property-based tests.

Profiles:
  ci      - fast, 100 examples per test (default for PR runs)
  nightly - thorough, 1000 examples per test

Select via environment variable:
  HYPOTHESIS_PROFILE=nightly pytest -m property
"""

import os
from hypothesis import HealthCheck, settings

settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "nightly",
    max_examples=1000,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile(
    "dev",
    max_examples=20,
    suppress_health_check=[HealthCheck.too_slow],
)

_profile = os.environ.get("HYPOTHESIS_PROFILE", "ci")
settings.load_profile(_profile)
