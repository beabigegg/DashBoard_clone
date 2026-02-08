# Migration Gates and Runbook

## Gate Checklist (Cutover Readiness)

A release is cutover-ready only when all gates pass:

1. Frontend build gate
- `npm --prefix frontend run build` succeeds
- expected artifacts exist in `src/mes_dashboard/static/dist/`

2. Root execution gate
- startup and deploy scripts run from repository root only
- no runtime dependency on any legacy subtree path

3. Functional parity gate
- resource-history frontend compute parity checks pass
- job-query/resource-history export headers match shared field contracts

4. Cache observability gate
- `/health` returns route cache telemetry and degraded flags
- `/health/deep` returns route cache telemetry for diagnostics
- `/health` includes `database_pool.runtime/state`, `degraded_reason`
- resource/wip derived index telemetry is visible (`resource_cache.derived_index`, `cache.derived_search_index`)

5. Runtime resilience gate
- pool exhaustion path returns `503` + `DB_POOL_EXHAUSTED` and `Retry-After`
- circuit-open path returns `503` + `CIRCUIT_BREAKER_OPEN` and fail-fast semantics
- frontend client does not aggressively retry on degraded pool exhaustion responses
- health/admin payloads expose worker policy state (`allowed`/`cooldown`/`blocked`) and alert booleans

6. Conda-systemd contract gate
- `deploy/mes-dashboard.service` and `deploy/mes-dashboard-watchdog.service` both run in the same conda runtime contract
- `WATCHDOG_RESTART_FLAG`, `WATCHDOG_PID_FILE`, `WATCHDOG_STATE_FILE` paths are consistent across app/admin/watchdog
- startup contract validation passes: `RUNTIME_CONTRACT_ENFORCE=true ./scripts/start_server.sh check`
- single-port bind (`GUNICORN_BIND`) remains stable during restart workflow

7. Regression gate
- focused unit/integration test subset passes (see validation evidence)

8. Documentation alignment gate
- `README.md` (and project-required mirror docs such as `README.mdj`) reflect current runtime architecture contract
- resilience diagnostics fields (thresholds/churn/recommendation) are documented for operators
- frontend shared-core governance updates are reflected in architecture notes

## Rollout Procedure

1. Prepare environment
- Activate conda env (`mes-dashboard`)
- install Python deps: `pip install -r requirements.txt`
- install frontend deps: `npm --prefix frontend install`

2. Build frontend artifacts
- `npm --prefix frontend run build`

3. Run migration gate tests
- execute focused pytest set covering templates/cache/contracts/health

4. Deploy with single-port mode
- start app with root `scripts/start_server.sh`
- verify portal and module pages render on same origin/port

5. Conda + systemd rehearsal (recommended before production cutover)
- `sudo cp deploy/mes-dashboard.service /etc/systemd/system/`
- `sudo cp deploy/mes-dashboard-watchdog.service /etc/systemd/system/`
- ensure deployment uses the same single env file: `/opt/mes-dashboard/.env`
- `sudo chown root:www-data /opt/mes-dashboard/.env && sudo chmod 640 /opt/mes-dashboard/.env`
- `sudo systemctl daemon-reload`
- `sudo systemctl enable --now mes-dashboard mes-dashboard-watchdog`
- call `/admin/api/worker/status` and verify runtime contract paths exist

6. Post-deploy checks
- call `/health` and `/health/deep`
- confirm route cache mode, degraded flags, and pool/runtime diagnostics align with environment (Redis on/off)
- trigger one controlled worker restart from admin API and verify single-port continuity
- verify guarded mode flow: blocked restart requires manual override payload (`manual_override`, `override_acknowledged`, `override_reason`)
- verify README architecture section matches deployed runtime contract

## Rollback Procedure

1. Trigger rollback criteria
- any critical gate failure after deployment (page unusable, export mismatch, health degradation beyond acceptable limits)

2. Operational rollback steps
- stop service: `scripts/start_server.sh stop`
- restore previously known-good build artifacts (or prior release package)
- restart service: `scripts/start_server.sh start`
- if using systemd: `sudo systemctl restart mes-dashboard mes-dashboard-watchdog`

3. Validation after rollback
- verify `/health` status is at least expected baseline
- re-run focused smoke tests for portal + key pages
- confirm CSV export downloads and headers
- verify degraded reason is cleared or matches expected dependency outage only

## Rollback Rehearsal Checklist

1. Simulate failure condition (e.g. invalid dist artifact deployment)
2. Execute stop/restore/start sequence
3. Verify health and page smoke checks
4. Capture timings and any manual intervention points
5. Update this runbook if any step was unclear or missing

## Alert Thresholds (Operational Contract)

Use these initial thresholds for alerting/escalation:

1. Sustained degraded state
- `degraded_reason` non-empty for >= 5 minutes

2. Worker restart churn
- >= 3 watchdog-triggered restarts within 10 minutes

3. Pool saturation pressure
- `database_pool.state.saturation >= 0.90` for >= 3 consecutive health probes

4. Frontend/API retry pressure
- significant increase of client retries for `DB_POOL_EXHAUSTED` or `CIRCUIT_BREAKER_OPEN` responses over baseline

5. Recovery policy blocked
- `resilience.policy_state.blocked == true` or `resilience.alerts.restart_blocked == true`
