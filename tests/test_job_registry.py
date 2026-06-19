# -*- coding: utf-8 -*-
"""Tests for job_registry.py — central async-job registry.

TDD: these tests are written before job_registry.py exists.
Each test resets _REGISTRY via autouse fixture to prevent order-dependence.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Isolation fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_registry(monkeypatch):
    """Reset _REGISTRY before every test to prevent order-dependence."""
    import mes_dashboard.services.job_registry as jr
    monkeypatch.setattr(jr, "_REGISTRY", {})
    yield


# ---------------------------------------------------------------------------
# TestJobRegistryModule — AC-1, AC-2
# ---------------------------------------------------------------------------

class TestJobRegistryModule:
    def test_module_exports_required_symbols(self):
        """AC-1: job_registry must export JobTypeConfig, register_job_type,
        get_job_type_config, list_registered_job_types, and _REGISTRY."""
        import mes_dashboard.services.job_registry as jr

        assert hasattr(jr, "JobTypeConfig"), "missing JobTypeConfig"
        assert hasattr(jr, "_REGISTRY"), "missing _REGISTRY"
        assert hasattr(jr, "register_job_type"), "missing register_job_type"
        assert hasattr(jr, "get_job_type_config"), "missing get_job_type_config"
        assert hasattr(jr, "list_registered_job_types"), "missing list_registered_job_types"

    def test_register_returns_stored_config(self):
        """AC-2: register_job_type stores config; get_job_type_config returns it."""
        from mes_dashboard.services.job_registry import (
            JobTypeConfig, register_job_type, get_job_type_config,
        )

        dummy_fn = MagicMock()
        config = JobTypeConfig(
            job_type="test-type",
            queue_name="test-queue",
            worker_fn=dummy_fn,
        )
        register_job_type(config)

        retrieved = get_job_type_config("test-type")
        assert retrieved is config
        assert retrieved.job_type == "test-type"
        assert retrieved.queue_name == "test-queue"
        assert retrieved.worker_fn is dummy_fn
        assert retrieved.timeout_seconds == 1800
        assert retrieved.ttl_seconds == 3600

    def test_get_returns_none_for_unknown_job_type(self):
        """AC-2: get_job_type_config returns None (not raise) for unknown type."""
        from mes_dashboard.services.job_registry import get_job_type_config

        result = get_job_type_config("nonexistent-type")
        assert result is None

    def test_list_returns_all_registered_types(self):
        """AC-2: list_registered_job_types returns all registered job_type strings."""
        from mes_dashboard.services.job_registry import (
            JobTypeConfig, register_job_type, list_registered_job_types,
        )

        fn_a = MagicMock()
        fn_b = MagicMock()
        register_job_type(JobTypeConfig(job_type="alpha", queue_name="q-alpha", worker_fn=fn_a))
        register_job_type(JobTypeConfig(job_type="beta", queue_name="q-beta", worker_fn=fn_b))

        types = list_registered_job_types()
        assert "alpha" in types
        assert "beta" in types
        assert len(types) == 2


# ---------------------------------------------------------------------------
# TestEnqueueJobDynamic — AC-3
# ---------------------------------------------------------------------------

class TestEnqueueJobDynamic:
    def test_dispatches_registered_job_type(self):
        """AC-3: enqueue_job_dynamic delegates to enqueue_job for a registered type."""
        from mes_dashboard.services.job_registry import (
            JobTypeConfig, register_job_type,
        )
        import mes_dashboard.services.async_query_job_service as svc

        dummy_fn = MagicMock()
        register_job_type(JobTypeConfig(
            job_type="test-dispatch",
            queue_name="test-dispatch-queue",
            worker_fn=dummy_fn,
            timeout_seconds=900,
            ttl_seconds=1800,
        ))

        mock_enqueue = MagicMock(return_value=("test-dispatch-abc123", None))
        with patch.object(svc, "enqueue_job", mock_enqueue):
            job_id, err = svc.enqueue_job_dynamic(
                "test-dispatch",
                owner="test-owner",
                params={"key": "value"},
            )

        assert job_id == "test-dispatch-abc123"
        assert err is None
        mock_enqueue.assert_called_once()

        call_kwargs = mock_enqueue.call_args.kwargs
        assert call_kwargs["queue_name"] == "test-dispatch-queue"
        assert call_kwargs["worker_fn"] is dummy_fn
        assert call_kwargs["owner"] == "test-owner"
        assert call_kwargs["prefix"] == "test-dispatch"
        assert call_kwargs["job_timeout"] == 900
        assert call_kwargs["result_ttl"] == 1800
        assert call_kwargs["kwargs"]["key"] == "value"

    def test_returns_error_tuple_for_unregistered_type(self):
        """AC-3: enqueue_job_dynamic returns (None, error_str) for unknown job type."""
        import mes_dashboard.services.async_query_job_service as svc

        job_id, err = svc.enqueue_job_dynamic(
            "nonexistent-type",
            owner="test-owner",
            params={},
        )

        assert job_id is None
        assert err is not None
        assert "nonexistent-type" in err

    def test_respects_should_enqueue_false(self):
        """AC-3: enqueue_job_dynamic returns (None, …) without calling queue when
        should_enqueue returns False."""
        from mes_dashboard.services.job_registry import (
            JobTypeConfig, register_job_type,
        )
        import mes_dashboard.services.async_query_job_service as svc

        dummy_fn = MagicMock()
        gate_fn = MagicMock(return_value=False)

        register_job_type(JobTypeConfig(
            job_type="gated-type",
            queue_name="gated-queue",
            worker_fn=dummy_fn,
            should_enqueue=gate_fn,
        ))

        mock_enqueue = MagicMock()
        with patch.object(svc, "enqueue_job", mock_enqueue):
            job_id, err = svc.enqueue_job_dynamic(
                "gated-type",
                owner="test-owner",
                params={"x": 1},
            )

        assert job_id is None
        assert err is not None
        mock_enqueue.assert_not_called()
        gate_fn.assert_called_once_with({"x": 1})


# ---------------------------------------------------------------------------
# TestJobServiceRegistrations — AC-4
# ---------------------------------------------------------------------------

class TestJobServiceRegistrations:
    def test_each_service_registers_exactly_one_job_type(self):
        """AC-4: importing all 8 job services registers exactly 8 distinct job types."""
        import mes_dashboard.services.job_registry as jr

        # Reset the registry cleanly (autouse fixture already did, but import order
        # may add entries during the module load cycle; we must import after reset).
        jr._REGISTRY.clear()

        # Import all 8 job services that call register_job_type at module end.
        # Using importlib.reload is not required since we cleared _REGISTRY and
        # the registration side-effect runs on the first import per process.
        # To force re-registration after clearing, we re-execute the module-level
        # register call by directly calling it, or we use the already-loaded modules.
        # The correct approach: call register_job_type from each service manually
        # because Python will not re-run module-level code on re-import.
        # Instead, we import the modules (their top-level register_job_type runs
        # on first import per session) — so we need importlib.reload here.
        import importlib

        import mes_dashboard.services.reject_query_job_service as rjs
        import mes_dashboard.services.yield_alert_job_service as yajs
        import mes_dashboard.services.production_history_job_service as phjs
        import mes_dashboard.services.trace_lineage_job_service as tljs
        import mes_dashboard.services.msd_seed_job_service as msd_seed
        import mes_dashboard.services.msd_lineage_job_service as msd_lin
        import mes_dashboard.services.material_consumption_service as mcs
        import mes_dashboard.services.material_trace_service as mts

        # Reload each to re-execute module-level register_job_type calls
        # against the cleared _REGISTRY.
        importlib.reload(rjs)
        importlib.reload(yajs)
        importlib.reload(phjs)
        importlib.reload(tljs)
        importlib.reload(msd_seed)
        importlib.reload(msd_lin)
        importlib.reload(mcs)
        importlib.reload(mts)

        registered = jr.list_registered_job_types()
        assert len(registered) == 8, (
            f"Expected 8 registered job types, got {len(registered)}: {registered}"
        )

        expected_types = {
            "reject",
            "yield_alert",
            "production_history",
            "trace-lineage",
            "msd-seed",
            "msd-lineage",
            "material-consumption",
            "material-trace",
        }
        assert set(registered) == expected_types, (
            f"Registered types mismatch.\n"
            f"Expected: {expected_types}\n"
            f"Got: {set(registered)}"
        )


# ---------------------------------------------------------------------------
# TestAlwaysAsyncField — IP-3: always_async field on JobTypeConfig
# ---------------------------------------------------------------------------

class TestAlwaysAsyncField:
    def test_job_type_config_always_async_defaults_false(self):
        """always_async defaults to False when not specified."""
        from mes_dashboard.services.job_registry import JobTypeConfig
        config = JobTypeConfig(
            job_type="test-default",
            queue_name="test-q",
            worker_fn=lambda: None,
        )
        assert config.always_async is False

    def test_job_type_config_always_async_true(self):
        """always_async can be set to True."""
        from mes_dashboard.services.job_registry import JobTypeConfig
        config = JobTypeConfig(
            job_type="test-always",
            queue_name="test-q",
            worker_fn=lambda: None,
            always_async=True,
        )
        assert config.always_async is True

    def test_eap_alarm_registered_with_always_async_true(self):
        """eap-alarm registration must have always_async=True."""
        import importlib
        import mes_dashboard.services.job_registry as jr
        import mes_dashboard.workers.eap_alarm_worker as w

        # Re-register against the currently-cleared registry
        importlib.reload(w)

        config = jr.get_job_type_config("eap-alarm")
        assert config is not None, "eap-alarm job type not registered"
        assert config.always_async is True, (
            f"Expected always_async=True, got {config.always_async}"
        )
