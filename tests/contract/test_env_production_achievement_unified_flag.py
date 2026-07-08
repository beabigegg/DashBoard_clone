# -*- coding: utf-8 -*-
"""Contract test: PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB env default pinned
to 'on' (production-achievement-async-spool, AC-5).

Verifies that:
1. The flag is documented in contracts/env/env-contract.md
2. The flag appears in contracts/env/.env.example.template with default 'on'
3. contracts/env/env.schema.json has the flag with enum + default='on'
4. The Flask-app-process module (routes) and RQ-worker-process module
   (worker) reference byte-identical env-var-name strings for the shared
   PRODUCTION_ACHIEVEMENT_* flags (source-level half of the gunicorn<->RQ
   worker env-var parity contract; env-contract.md §Worker Feature-Flag
   Env-Var Parity).

Per test-discipline: pin exact default value, not just var-name presence.
Pattern mirrors tests/contract/test_env_downtime_unified_flag.py -- unlike
DOWNTIME_USE_UNIFIED_JOB (default 'off'), PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB
defaults 'on' with NO legacy code path behind 'off' (clean pre-launch
replacement; 'off' is a pure kill switch, see env-contract.md).
"""
from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "contracts" / "env"
_ENV_CONTRACT = _CONTRACTS_DIR / "env-contract.md"
_ENV_EXAMPLE = _CONTRACTS_DIR / ".env.example.template"
_ENV_SCHEMA = _CONTRACTS_DIR / "env.schema.json"

_EXPECTED_KEY = "PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB"
_EXPECTED_DEFAULT = "on"


class TestProductionAchievementUnifiedFlagInEnvContract:
    """AC-5: Flag must be documented in env-contract.md."""

    def test_flag_in_env_contract_md(self):
        """PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB must appear in env-contract.md."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        assert _EXPECTED_KEY in content, (
            f"{_EXPECTED_KEY} not found in contracts/env/env-contract.md (AC-5)"
        )

    def test_flag_documented_with_default_on_in_contract_md(self):
        """env-contract.md must document the 'on' default for the flag."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        key_idx = content.find(_EXPECTED_KEY)
        assert key_idx != -1, f"{_EXPECTED_KEY} not in env-contract.md"
        section = content[key_idx : key_idx + 500]
        assert "on" in section.lower(), (
            f"env-contract.md: expected 'on' default near {_EXPECTED_KEY} section"
        )

    def test_worker_queue_and_timeout_vars_documented(self):
        """PRODUCTION_ACHIEVEMENT_WORKER_QUEUE / _JOB_TIMEOUT_SECONDS documented."""
        content = _ENV_CONTRACT.read_text(encoding="utf-8")
        for var in ("PRODUCTION_ACHIEVEMENT_WORKER_QUEUE", "PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS"):
            assert var in content, f"{var} not found in contracts/env/env-contract.md (AC-5)"


class TestProductionAchievementUnifiedFlagInEnvExample:
    """AC-5: Flag must be present with default=on in .env.example.template."""

    def test_flag_in_env_example_template(self):
        """PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB= line must exist in .env.example.template."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        assert _EXPECTED_KEY + "=" in content, (
            f"{_EXPECTED_KEY}= not found in contracts/env/.env.example.template (AC-5)"
        )

    def test_flag_default_is_on_in_env_example_template(self):
        """Default value in .env.example.template must be exactly 'on'."""
        content = _ENV_EXAMPLE.read_text(encoding="utf-8")
        assert f"{_EXPECTED_KEY}=on" in content, (
            f"Expected '{_EXPECTED_KEY}=on' in .env.example.template (AC-5)"
        )


class TestProductionAchievementUnifiedFlagInSchema:
    """AC-5: Flag must be registered in env.schema.json with enum + default='on'."""

    def test_flag_in_schema_json(self):
        """PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB must be a property in env.schema.json."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        assert _EXPECTED_KEY in schema.get("properties", {}), (
            f"{_EXPECTED_KEY} not in env.schema.json properties (AC-5)"
        )

    def test_flag_default_is_on_in_schema(self):
        """Default in env.schema.json must be exactly 'on'."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"].get(_EXPECTED_KEY, {})
        assert prop.get("default") == _EXPECTED_DEFAULT, (
            f"env.schema.json: {_EXPECTED_KEY} default must be '{_EXPECTED_DEFAULT}', "
            f"got {prop.get('default')!r} (AC-5)"
        )

    def test_flag_enum_includes_off_and_on(self):
        """Schema enum must include both 'off' and 'on' values."""
        schema = json.loads(_ENV_SCHEMA.read_text(encoding="utf-8"))
        prop = schema["properties"].get(_EXPECTED_KEY, {})
        enum = prop.get("enum", [])
        assert "off" in enum, f"Schema enum missing 'off': {enum}"
        assert "on" in enum, f"Schema enum missing 'on': {enum}"


class TestGunicornWorkerParity:
    """AC-5: the Flask-app-process module (gunicorn) and the RQ-worker-process
    module must reference byte-identical env-var-name strings for the shared
    PRODUCTION_ACHIEVEMENT_* flags -- a name typo/drift here silently breaks
    job-type registration parity between the two processes (env-contract.md
    §Worker Feature-Flag Env-Var Parity).

    The deploy/*.service-level static check (grep for a hardcoded
    Environment= override that would split-brain the two processes) is
    owned by ci-cd-gatekeeper (ci-gates.md worker-env-parity-static gate);
    this test covers the source-level half of the parity contract.
    """

    def test_gunicorn_conf_and_rq_worker_preload_reference_same_flag_names(self):
        routes_src = (
            _REPO_ROOT / "src/mes_dashboard/routes/production_achievement_routes.py"
        ).read_text(encoding="utf-8")
        worker_src = (
            _REPO_ROOT / "src/mes_dashboard/workers/production_achievement_worker.py"
        ).read_text(encoding="utf-8")
        contract = _ENV_CONTRACT.read_text(encoding="utf-8")

        # The route module (loaded into the gunicorn/Flask app process) reads
        # the unified-job kill switch.
        assert '"PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB"' in routes_src, (
            "production_achievement_routes.py must read PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB "
            "via the exact contract-documented name"
        )
        # The worker module (loaded into the RQ worker process) reads the
        # queue name + timeout using the exact same name strings gunicorn's
        # shared .env / env-contract.md document.
        assert '"PRODUCTION_ACHIEVEMENT_WORKER_QUEUE"' in worker_src, (
            "production_achievement_worker.py must read PRODUCTION_ACHIEVEMENT_WORKER_QUEUE "
            "via the exact contract-documented name"
        )
        assert '"PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS"' in worker_src, (
            "production_achievement_worker.py must read PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS "
            "via the exact contract-documented name"
        )

        # gunicorn.conf.py must NOT itself hardcode a PRODUCTION_ACHIEVEMENT_*
        # value -- both processes resolve these flags solely from the shared
        # environment (EnvironmentFile), never a Python-level override.
        gunicorn_conf_src = (_REPO_ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")
        assert "PRODUCTION_ACHIEVEMENT" not in gunicorn_conf_src, (
            "gunicorn.conf.py must not hardcode any PRODUCTION_ACHIEVEMENT_* value -- "
            "both the gunicorn app process and the RQ worker process must resolve "
            "these flags solely from the shared environment (env-contract.md parity rule)"
        )

        # Every PRODUCTION_ACHIEVEMENT_* name referenced by source must also be
        # documented in env-contract.md (no undocumented drift).
        for var in (
            "PRODUCTION_ACHIEVEMENT_USE_UNIFIED_JOB",
            "PRODUCTION_ACHIEVEMENT_WORKER_QUEUE",
            "PRODUCTION_ACHIEVEMENT_JOB_TIMEOUT_SECONDS",
        ):
            assert var in contract, f"{var} must be documented in env-contract.md (AC-5)"
