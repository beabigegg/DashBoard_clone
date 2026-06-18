# -*- coding: utf-8 -*-
"""Flask application factory for MES Dashboard."""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import threading
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for

from mes_dashboard.config.settings import get_config
from mes_dashboard.core.cache import create_default_cache_backend
from mes_dashboard.core.database import (
    get_table_data,
    get_table_columns,
    get_engine,
    init_db,
    start_keepalive,
    dispose_engine,
    install_log_redaction_filter,
)
from mes_dashboard.core.permissions import is_admin_logged_in, is_user_logged_in, _is_ajax_request
from mes_dashboard.core.csrf import (
    get_csrf_token,
    should_enforce_csrf,
    validate_csrf,
)
from mes_dashboard.routes import register_routes
from mes_dashboard.routes.user_auth_routes import user_auth_bp
from mes_dashboard.routes.admin_routes import admin_bp
from mes_dashboard.routes.health_routes import health_bp
from mes_dashboard.services.page_registry import (
    get_navigation_config,
    get_page_status,
    is_api_public,
)
from mes_dashboard.core.cache_updater import start_cache_updater, stop_cache_updater
from mes_dashboard.services.realtime_equipment_cache import (
    init_realtime_equipment_cache,
    stop_equipment_status_sync_worker,
)
from mes_dashboard.services.scrap_reason_exclusion_cache import (
    init_scrap_reason_exclusion_cache,
    stop_scrap_reason_exclusion_cache_worker,
)
from mes_dashboard.core.query_spool_store import (
    init_query_spool_cleanup,
    stop_query_spool_cleanup_worker,
)
from mes_dashboard.services.anomaly_detection_scheduler import (
    init_anomaly_detection_scheduler,
    stop_anomaly_detection_scheduler,
)
from mes_dashboard.core.modernization_policy import (
    get_deferred_routes as get_deferred_routes_from_scope_matrix,
    get_missing_in_scope_assets,
    is_asset_readiness_enforced,
    missing_in_scope_asset_response,
    maybe_redirect_to_canonical_shell,
)
from mes_dashboard.core.feature_flags import resolve_bool_flag
from mes_dashboard.core.redis_client import close_redis
from mes_dashboard.core.runtime_contract import build_runtime_contract_diagnostics


_SHUTDOWN_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False
_SHELL_ROUTE_CONTRACT_LOCK = threading.Lock()
_SHELL_ROUTE_CONTRACT_MAP: dict[str, dict[str, object]] | None = None


def _configure_logging(app: Flask) -> None:
    """Configure application logging.

    Sets up logging to stderr (captured by Gunicorn's --capture-output).
    Additionally sets up SQLite log store for admin dashboard queries.

    Log levels:
    - DEBUG: Query completion times, connection events
    - WARNING: Slow queries (>1s)
    - ERROR: Connection failures, query errors with ORA codes
    """
    # Configure the mes_dashboard logger
    logger = logging.getLogger('mes_dashboard')
    logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

    # Only add handler if not already configured (avoid duplicates)
    if not logger.handlers:
        # Console handler (stderr - captured by Gunicorn)
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # SQLite log handler for admin dashboard (INFO level and above)
        try:
            from mes_dashboard.core.log_store import get_sqlite_log_handler, LOG_STORE_ENABLED
            if LOG_STORE_ENABLED:
                sqlite_handler = get_sqlite_log_handler()
                sqlite_handler.setLevel(logging.INFO)
                logger.addHandler(sqlite_handler)
                logger.debug("SQLite log handler registered")
        except Exception as e:
            logger.warning(f"Failed to initialize SQLite log handler: {e}")

    # Prevent propagation to root logger (avoid duplicate logs)
    logger.propagate = False
    install_log_redaction_filter(logger)


def _is_production_env(app: Flask) -> bool:
    env_value = str(app.config.get("ENV") or os.getenv("FLASK_ENV") or "production").lower()
    return env_value in {"prod", "production"}


def _build_security_headers(*, allow_unsafe_eval: bool = False) -> dict[str, str]:
    script_directives = ["'self'", "'unsafe-inline'", "'wasm-unsafe-eval'"]
    if allow_unsafe_eval:
        script_directives.append("'unsafe-eval'")

    headers = {
        "Content-Security-Policy": (
            "default-src 'self'; "
            f"script-src {' '.join(script_directives)}; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://extensions.duckdb.org; "
            "worker-src 'self' blob:; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        ),
        "X-Frame-Options": "SAMEORIGIN",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    return headers


def _resolve_trusted_proxy_ips(app: Flask) -> tuple[str, ...]:
    configured_sources = os.getenv("TRUSTED_PROXY_IPS")
    if configured_sources is None:
        configured_sources = app.config.get("TRUSTED_PROXY_IPS")
    if isinstance(configured_sources, str):
        return tuple(
            part.strip()
            for part in configured_sources.split(",")
            if part.strip()
        )
    return tuple(configured_sources or ())


def _is_request_secure(app: Flask) -> bool:
    if request.is_secure:
        return True

    trust_proxy_headers = resolve_bool_flag(
        "TRUST_PROXY_HEADERS",
        config=app.config,
        default=bool(app.config.get("TRUST_PROXY_HEADERS", False)),
    )
    if not trust_proxy_headers:
        return False

    trusted_sources = set(_resolve_trusted_proxy_ips(app))
    remote_addr = request.remote_addr or ""
    if trusted_sources and remote_addr not in trusted_sources:
        return False

    forwarded_proto = str(request.headers.get("X-Forwarded-Proto", "")).split(",")[0].strip().lower()
    if forwarded_proto == "https":
        return True

    forwarded_ssl = str(request.headers.get("X-Forwarded-Ssl", "")).strip().lower()
    return forwarded_ssl in {"on", "1", "true"}


def _normalize_session_cookie_security(
    response,
    *,
    secure: bool,
    session_cookie_name: str,
):
    set_cookie_headers = response.headers.getlist("Set-Cookie")
    if not set_cookie_headers:
        return

    prefix = f"{session_cookie_name}="
    updated_headers: list[str] = []
    for raw_cookie in set_cookie_headers:
        if not raw_cookie.startswith(prefix):
            updated_headers.append(raw_cookie)
            continue

        parts = [part.strip() for part in raw_cookie.split(";")]
        has_secure = any(part.lower() == "secure" for part in parts[1:])
        if secure and not has_secure:
            parts.append("Secure")
        elif not secure and has_secure:
            parts = [part for part in parts if part.lower() != "secure"]

        updated_headers.append("; ".join(parts))

    response.headers.setlist("Set-Cookie", updated_headers)


def _resolve_secret_key(app: Flask) -> str:
    env_name = str(app.config.get("ENV") or os.getenv("FLASK_ENV") or "development").lower()
    configured = os.environ.get("SECRET_KEY") or app.config.get("SECRET_KEY")
    insecure_defaults = {"", "dev-secret-key-change-in-prod"}

    if configured and configured not in insecure_defaults:
        return configured

    if env_name in {"production", "prod"}:
        raise RuntimeError(
            "SECRET_KEY is required in production and cannot use insecure defaults."
        )

    # Development and testing get explicit environment-safe defaults.
    if env_name in {"testing", "test"}:
        return "test-secret-key"
    return "dev-local-only-secret-key"


def _validate_production_security_settings(app: Flask) -> None:
    """Validate production security-sensitive runtime settings."""
    if not _is_production_env(app):
        return

    trust_proxy_headers = resolve_bool_flag(
        "TRUST_PROXY_HEADERS",
        config=app.config,
        default=bool(app.config.get("TRUST_PROXY_HEADERS", False)),
    )
    if trust_proxy_headers:
        trusted_sources = _resolve_trusted_proxy_ips(app)
        if not trusted_sources:
            raise RuntimeError(
                "TRUST_PROXY_HEADERS=true requires TRUSTED_PROXY_IPS in production."
            )


def _resolve_csp_allow_unsafe_eval(app: Flask) -> bool:
    return resolve_bool_flag(
        "CSP_ALLOW_UNSAFE_EVAL",
        config=app.config,
        default=bool(app.config.get("CSP_ALLOW_UNSAFE_EVAL", False)),
    )


def _resolve_portal_spa_enabled(app: Flask) -> bool:
    """Resolve cutover flag for SPA shell navigation.

    Environment variable takes precedence so operators can toggle behavior
    without code changes during migration rehearsal/cutover.
    """
    return resolve_bool_flag(
        "PORTAL_SPA_ENABLED",
        config=app.config,
        default=bool(app.config.get("PORTAL_SPA_ENABLED", False)),
    )


def _can_view_page_for_user(route: str, *, is_admin: bool) -> bool:
    """Mirror portal page visibility policy for shell navigation/API."""
    status = get_page_status(route)
    if status is None:
        return True
    if status == "released":
        return True
    return is_admin


def _safe_order(value: object, default: int = 9999) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _load_shell_route_contract_map() -> dict[str, dict[str, object]]:
    """Load shell route contract map used for navigation diagnostics."""
    global _SHELL_ROUTE_CONTRACT_MAP
    with _SHELL_ROUTE_CONTRACT_LOCK:
        if _SHELL_ROUTE_CONTRACT_MAP is not None:
            return _SHELL_ROUTE_CONTRACT_MAP

        project_root = Path(__file__).resolve().parents[2]
        contract_candidates = [
            project_root
            / "docs"
            / "migration"
            / "full-modernization-architecture-blueprint"
            / "route_contracts.json",
            project_root
            / "docs"
            / "migration"
            / "portal-shell-route-view-integration"
            / "route_migration_contract.json",
        ]

        contract_map: dict[str, dict[str, object]] = {}
        logger = logging.getLogger("mes_dashboard")
        for index, contract_file in enumerate(contract_candidates):
            if not contract_file.exists():
                continue
            try:
                payload = json.loads(contract_file.read_text(encoding="utf-8"))
                routes = payload.get("routes", [])
                for item in routes:
                    if not isinstance(item, dict):
                        continue
                    route = str(item.get("route", "")).strip()
                    if route.startswith("/"):
                        contract_map[route] = dict(item)
                if contract_map:
                    if index > 0:
                        logger.warning(
                            "Using legacy contract file fallback for shell route contracts: %s",
                            contract_file,
                        )
                    break
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Failed to load shell route contract from %s: %s",
                    contract_file,
                    exc,
                )

        _SHELL_ROUTE_CONTRACT_MAP = contract_map
        return _SHELL_ROUTE_CONTRACT_MAP


def _load_shell_route_contract_routes() -> set[str]:
    return set(_load_shell_route_contract_map().keys())


def _load_shell_deferred_routes() -> set[str]:
    contract_map = _load_shell_route_contract_map()
    deferred_from_contract = {
        route
        for route, metadata in contract_map.items()
        if str(metadata.get("scope", "")).strip() == "deferred"
    }
    deferred_from_scope = set(get_deferred_routes_from_scope_matrix())
    return deferred_from_contract | deferred_from_scope


def _validate_spool_dir(app: Flask) -> None:
    """Warn if QUERY_SPOOL_DIR is missing, not writable, or not a shared mount.

    Does NOT raise — the app starts regardless.  This validation is advisory only
    and surfaces misconfigurations early in the log so operators notice before
    the first real query hits a spool-write failure.
    """
    logger = logging.getLogger("mes_dashboard")
    raw_dir = os.getenv("QUERY_SPOOL_DIR", "tmp/query_spool")
    spool_path = Path(raw_dir).resolve()

    # 1. Directory existence and writability.
    if not spool_path.exists():
        logger.warning(
            "QUERY_SPOOL_DIR does not exist: %s  "
            "(spool writes will fail until the directory is created)",
            spool_path,
        )
    elif not os.access(spool_path, os.W_OK):
        logger.warning(
            "QUERY_SPOOL_DIR exists but is not writable: %s  "
            "(spool writes will fail — check directory permissions)",
            spool_path,
        )

    # 2. Cross-worker sharing heuristic.
    #    Paths under /tmp or relative paths are process-local on most deployments
    #    and will NOT be visible to other Gunicorn workers or Docker sidecars.
    raw_stripped = raw_dir.strip()
    is_under_tmp = spool_path.parts[0:2] == (os.sep, "tmp") if spool_path.is_absolute() else False
    is_relative = not os.path.isabs(raw_stripped)

    if is_relative:
        logger.warning(
            "QUERY_SPOOL_DIR is a relative path (%r → %s).  "
            "Relative paths resolve against the process working directory, which may "
            "differ across Gunicorn workers or Docker containers.  "
            "Set QUERY_SPOOL_DIR to a shared absolute mount path for multi-worker deployments.",
            raw_stripped,
            spool_path,
        )
    elif is_under_tmp:
        logger.warning(
            "QUERY_SPOOL_DIR resolves under /tmp (%s).  "
            "/tmp is typically process-local (tmpfs) and NOT shared across containers or workers.  "
            "Use a shared volume mount (e.g. /var/lib/mes_dashboard/spool) in production.",
            spool_path,
        )


def _validate_in_scope_asset_readiness(app: Flask) -> None:
    """Validate in-scope dist assets and enforce fail-fast policy when configured."""
    dist_dir = Path(app.static_folder or "") / "dist"
    missing_assets = get_missing_in_scope_assets(dist_dir)
    diagnostics = {
        "dist_dir": str(dist_dir),
        "missing_in_scope_assets": missing_assets,
        "enforced": False,
    }
    app.extensions["asset_readiness"] = diagnostics
    if not missing_assets:
        return

    with app.app_context():
        enforced = is_asset_readiness_enforced()
    diagnostics["enforced"] = enforced

    message = "In-scope asset readiness check failed: " + ", ".join(missing_assets)
    if enforced:
        raise RuntimeError(message)
    logging.getLogger("mes_dashboard").warning(message)


def _shutdown_runtime_resources() -> None:
    """Stop background workers and shared clients during app/worker shutdown."""
    logger = logging.getLogger("mes_dashboard")

    try:
        stop_cache_updater()
    except Exception as exc:
        logger.warning("Error stopping cache updater: %s", exc)

    try:
        stop_equipment_status_sync_worker()
    except Exception as exc:
        logger.warning("Error stopping equipment sync worker: %s", exc)

    try:
        stop_scrap_reason_exclusion_cache_worker()
    except Exception as exc:
        logger.warning("Error stopping scrap exclusion cache worker: %s", exc)

    try:
        stop_query_spool_cleanup_worker()
    except Exception as exc:
        logger.warning("Error stopping query spool cleanup worker: %s", exc)

    try:
        stop_anomaly_detection_scheduler()
    except Exception as exc:
        logger.warning("Error stopping anomaly detection scheduler: %s", exc)

    try:
        from mes_dashboard.core.metrics_history import stop_metrics_history
        stop_metrics_history()
    except Exception as exc:
        logger.warning("Error stopping metrics history: %s", exc)

    try:
        from mes_dashboard.core.login_session_store import get_login_session_store
        get_login_session_store().close_all_active_sessions()
    except Exception as exc:
        logger.warning("Error closing active login sessions on shutdown: %s", exc)

    try:
        from mes_dashboard.core.sync_worker import stop_sync_worker
        stop_sync_worker()
    except Exception as exc:
        logger.warning("Error stopping sync worker: %s", exc)

    try:
        from mes_dashboard.core.mysql_client import dispose_mysql_engine
        dispose_mysql_engine()
    except Exception as exc:
        logger.warning("Error disposing MySQL engine: %s", exc)

    try:
        close_redis()
    except Exception as exc:
        logger.warning("Error closing Redis client: %s", exc)

    try:
        dispose_engine()
    except Exception as exc:
        logger.warning("Error disposing DB engines: %s", exc)


def _register_shutdown_hooks(app: Flask) -> None:
    global _ATEXIT_REGISTERED

    app.extensions["runtime_shutdown"] = _shutdown_runtime_resources
    if app.extensions.get("runtime_shutdown_registered"):
        return

    app.extensions["runtime_shutdown_registered"] = True
    if app.testing or bool(app.config.get("TESTING")) or os.getenv("PYTEST_CURRENT_TEST"):
        return

    with _SHUTDOWN_LOCK:
        if not _ATEXIT_REGISTERED:
            atexit.register(_shutdown_runtime_resources)
            _ATEXIT_REGISTERED = True


def _is_runtime_contract_enforced(app: Flask) -> bool:
    return resolve_bool_flag(
        "RUNTIME_CONTRACT_ENFORCE",
        config=app.config,
        default=_is_production_env(app),
    )


def _validate_runtime_contract(app: Flask) -> None:
    strict = _is_runtime_contract_enforced(app)
    diagnostics = build_runtime_contract_diagnostics(strict=strict)
    app.extensions["runtime_contract"] = diagnostics["contract"]
    app.extensions["runtime_contract_validation"] = {
        "valid": diagnostics["valid"],
        "strict": diagnostics["strict"],
        "errors": diagnostics["errors"],
    }

    if diagnostics["valid"]:
        return

    message = "Runtime contract validation failed: " + "; ".join(diagnostics["errors"])
    if strict:
        raise RuntimeError(message)
    logging.getLogger("mes_dashboard").warning(message)


class _NaNSafeJSONProvider(Flask.json_provider_class):  # type: ignore[misc]
    """JSON provider that converts NaN/Infinity to null.

    Pandas DataFrames produce float('nan') for NULL database columns.
    Standard json.dumps serialises these as the literal ``NaN``, which
    is invalid JSON and causes ``Unexpected token 'N'`` in browsers.
    """

    def dumps(self, obj, **kwargs):
        """Serialize *obj*, replacing NaN/Infinity with None first."""
        return super().dumps(_sanitize_nan(obj), **kwargs)


def _sanitize_nan(obj):
    """Recursively replace float NaN/Infinity with None."""
    import math

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _reinit_sqlite_handles() -> None:
    """Close inherited (pre-fork) thread-local SQLite connections in each worker.

    Called from post_fork() in gunicorn.conf.py.  After ``fork()``, the child
    process inherits a raw copy of every open file descriptor from the master.
    SQLite's thread-local connections are not fork-safe: two processes sharing
    the same file descriptor for WAL writes produce undefined behaviour.

    This function clears the thread-local ``connection`` attribute on each
    SQLite-backed singleton so that the worker's next ``_get_connection()``
    call opens a fresh fd (not the inherited one).

    Guard: returns immediately when ``FLASK_TESTING`` is set so that test
    suites — which import app.py but never fork — are not affected.

    Design reference: implementation-plan.md IP-5.
    """
    if os.environ.get("FLASK_TESTING"):
        return

    _log = logging.getLogger("mes_dashboard.post_fork")

    # log_store
    try:
        from mes_dashboard.core.log_store import get_log_store
        store = get_log_store()
        if hasattr(store, '_local') and hasattr(store._local, 'connection'):
            try:
                if store._local.connection is not None:
                    store._local.connection.close()
            except Exception:
                pass
            store._local.connection = None
    except Exception as exc:
        _log.warning("_reinit_sqlite_handles: log_store reset failed: %s", exc)

    # login_session_store
    try:
        from mes_dashboard.core.login_session_store import get_login_session_store
        store_lss = get_login_session_store()
        if hasattr(store_lss, '_local') and hasattr(store_lss._local, 'connection'):
            try:
                if store_lss._local.connection is not None:
                    store_lss._local.connection.close()
            except Exception:
                pass
            store_lss._local.connection = None
    except Exception as exc:
        _log.warning("_reinit_sqlite_handles: login_session_store reset failed: %s", exc)

    # metrics_history
    try:
        from mes_dashboard.core.metrics_history import get_metrics_history_store
        store_mh = get_metrics_history_store()
        if hasattr(store_mh, '_local') and hasattr(store_mh._local, 'connection'):
            try:
                if store_mh._local.connection is not None:
                    store_mh._local.connection.close()
            except Exception:
                pass
            store_mh._local.connection = None
    except Exception as exc:
        _log.warning("_reinit_sqlite_handles: metrics_history reset failed: %s", exc)


def _start_per_worker_services(worker=None) -> None:
    """Start all per-worker background threads after post_fork.

    Called from post_fork() in gunicorn.conf.py inside each gunicorn worker.
    Threads do not survive fork(), so every background thread that ran in the
    master (before preload_app fork) must be re-started here in the worker.

    Prewarm calls (start_parts_cache_warmup) intentionally remain in
    create_app() — they run ONCE in the master under preload_app=True and
    must NOT be called here.  DuckDB prewarms for resource-history and
    downtime-analysis now go through the RQ warmup queue instead.

    Guard: returns immediately when ``FLASK_TESTING`` is set so that test
    suites do not start real background threads.

    Design reference: implementation-plan.md IP-4.
    """
    if os.environ.get("FLASK_TESTING"):
        return

    _log = logging.getLogger("mes_dashboard.post_fork")

    # Warm up the Oracle engine pool for this worker (each worker gets its own
    # pool after dispose_engine() in post_fork).
    try:
        get_engine()
    except Exception as exc:
        _log.warning("_start_per_worker_services: get_engine failed: %s", exc)

    # Keep-alive ping thread for Oracle connections.
    try:
        start_keepalive()
    except Exception as exc:
        _log.warning("_start_per_worker_services: start_keepalive failed: %s", exc)

    # Redis cache updater thread.
    try:
        start_cache_updater()
    except Exception as exc:
        _log.warning("_start_per_worker_services: start_cache_updater failed: %s", exc)

    # Resolve the Flask app instance (set by create_app() into _APP_INSTANCE).
    # Using the module-level variable avoids circular imports (we are already
    # inside mes_dashboard.app — referencing _APP_INSTANCE directly is safe).
    _app = _APP_INSTANCE  # may be None before create_app() has completed

    try:
        init_realtime_equipment_cache(_app)
    except Exception as exc:
        _log.warning("_start_per_worker_services: init_realtime_equipment_cache failed: %s", exc)

    # Scrap-reason exclusion cache sync thread.
    try:
        init_scrap_reason_exclusion_cache(_app)
    except Exception as exc:
        _log.warning("_start_per_worker_services: init_scrap_reason_exclusion_cache failed: %s", exc)

    # Parquet spool cleanup worker.
    try:
        init_query_spool_cleanup(_app)
    except Exception as exc:
        _log.warning("_start_per_worker_services: init_query_spool_cleanup failed: %s", exc)

    # Anomaly detection scheduler.
    try:
        init_anomaly_detection_scheduler(_app)
    except Exception as exc:
        _log.warning("_start_per_worker_services: init_anomaly_detection_scheduler failed: %s", exc)

    # Spool warmup scheduler (leader-elected via Redis lock; safe to call from every worker).
    try:
        from mes_dashboard.core.spool_warmup_scheduler import init_warmup_scheduler
        init_warmup_scheduler(_app)
    except Exception as exc:
        _log.warning("_start_per_worker_services: init_warmup_scheduler failed: %s", exc)

    # Metrics history collector thread.
    try:
        from mes_dashboard.core.metrics_history import start_metrics_history
        start_metrics_history(_app)
    except Exception as exc:
        _log.warning("_start_per_worker_services: start_metrics_history failed: %s", exc)

    # RSS memory guard thread.
    try:
        from mes_dashboard.core.worker_memory_guard import start_worker_memory_guard
        start_worker_memory_guard()
    except Exception as exc:
        _log.warning("_start_per_worker_services: start_worker_memory_guard failed: %s", exc)

    # LoginSessionStore initialisation (creates the SQLite schema if missing).
    try:
        from mes_dashboard.core.login_session_store import get_login_session_store
        get_login_session_store()
    except Exception as exc:
        _log.warning("_start_per_worker_services: get_login_session_store failed: %s", exc)

    # MySQL dual-layer sync (optional, controlled by MYSQL_OPS_ENABLED).
    try:
        from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED
        if MYSQL_OPS_ENABLED:
            try:
                from mes_dashboard.core.mysql_client import get_mysql_engine
                get_mysql_engine()
                from mes_dashboard.core.sync_worker import start_sync_worker
                start_sync_worker()
            except Exception as _mysql_exc:
                _log.warning(
                    "MySQL OPS init failed in post_fork (system continues in SQLite-only mode): %s",
                    _mysql_exc,
                )
    except Exception as exc:
        _log.warning("_start_per_worker_services: MYSQL_OPS_ENABLED check failed: %s", exc)


# Module-level reference to the Flask app instance, set in create_app() so that
# _start_per_worker_services() (called from post_fork, which has no app argument)
# can pass the correct Flask app to services that require an app context.
_APP_INSTANCE: "Flask | None" = None


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask app instance."""
    app = Flask(__name__, template_folder="templates")
    app.json_provider_class = _NaNSafeJSONProvider
    app.json = _NaNSafeJSONProvider(app)

    config_class = get_config(config_name)
    app.config.from_object(config_class)
    app.config["PORTAL_SPA_ENABLED"] = _resolve_portal_spa_enabled(app)
    _max_body_mb = int(os.getenv("MAX_REQUEST_BODY_MB", "2"))
    app.config["MAX_CONTENT_LENGTH"] = _max_body_mb * 1024 * 1024
    is_production = _is_production_env(app)

    # Session configuration with environment-aware secret validation.
    app.secret_key = _resolve_secret_key(app)
    app.config["SECRET_KEY"] = app.secret_key
    _validate_production_security_settings(app)

    # Session cookie security settings
    # Always normalize Secure flag in after_request using actual request scheme.
    app.config['SESSION_COOKIE_SECURE'] = False
    # HTTPONLY: Prevent JavaScript access to session cookie (XSS protection)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    # SAMESITE: strict in production, relaxed for local development usability.
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict' if is_production else 'Lax'
    # Permanent session lifetime: 8 hours (one shift), matching LDAP JWT validity.
    from datetime import timedelta
    _lifetime_seconds = int(os.getenv("PERMANENT_SESSION_LIFETIME", "28800"))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=_lifetime_seconds)

    # Configure logging first
    _configure_logging(app)
    _validate_runtime_contract(app)
    _validate_spool_dir(app)
    _validate_in_scope_asset_readiness(app)
    security_headers = _build_security_headers(
        allow_unsafe_eval=_resolve_csp_allow_unsafe_eval(app),
    )
    # CORS: 解析 CORS_ALLOWED_ORIGINS 環境變數（逗號分隔的來源清單）
    # 同源架構（單 Port）無需設定；開發時 Vite dev server 跨 port 才需要
    _cors_allowed_origins: frozenset[str] = frozenset(
        o.strip()
        for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
        if o.strip()
    )

    # Route-level cache backend (L1 memory + optional L2 Redis)
    app.extensions["cache"] = create_default_cache_backend()

    # Initialize database teardown and pool
    init_db(app)
    running_pytest = bool(os.getenv("PYTEST_CURRENT_TEST"))
    is_testing_runtime = bool(app.config.get("TESTING")) or app.testing or running_pytest
    with app.app_context():
        # Shared-volume probe is written unconditionally (even in testing mode) so
        # that real-environment integration tests can verify cross-worker visibility.
        # The background check is only launched in production to avoid polluting logs.
        try:
            from mes_dashboard.core.spool_dir_check import write_pid_probe, check_shared_volume
            write_pid_probe()
            if not is_testing_runtime:
                threading.Thread(
                    target=check_shared_volume,
                    kwargs={"timeout": 30},
                    daemon=True,
                    name="spool-volume-check",
                ).start()
        except Exception as _spool_chk_exc:
            logging.getLogger("mes_dashboard").warning(
                "spool_dir_check init failed (non-fatal): %s", _spool_chk_exc
            )
        if not is_testing_runtime:
            # --------------------------------------------------------
            # SINGLE-RUN prewarm tasks (run ONCE in the master under
            # preload_app=True — must NOT be called from post_fork /
            # _start_per_worker_services).
            # --------------------------------------------------------

            # resource-history DuckDB prewarm and downtime-analysis DuckDB prewarm
            # are now handled by the RQ warmup queue (_WARMUP_JOBS in
            # spool_warmup_scheduler.py) — daemon-thread calls removed (unify-duckdb-prewarm-rq).

            # Pre-warm material-consumption parts list Redis cache.
            from mes_dashboard.services.material_consumption_service import start_parts_cache_warmup
            start_parts_cache_warmup()

            # --------------------------------------------------------
            # PER-WORKER services: also started here for the non-preload
            # path (flask run / direct gunicorn without preload_app).
            # Under preload_app=True, post_fork calls
            # _start_per_worker_services() instead — these lines run in
            # the master but threads die on fork(); the workers get a
            # fresh set from post_fork.
            #
            # NOTE: if we did NOT set preload_app=True (or ran via
            # ``flask run``), this block is the only startup path and
            # must remain complete here.
            # --------------------------------------------------------
            get_engine()
            start_keepalive()  # Keep database connections alive
            start_cache_updater()  # Start Redis cache updater
            init_realtime_equipment_cache(app)  # Start realtime equipment status cache
            init_scrap_reason_exclusion_cache(app)  # Start exclusion-policy cache sync
            init_query_spool_cleanup(app)  # Start parquet spool cleanup worker
            init_anomaly_detection_scheduler(app)  # Start anomaly detection scheduler
            from mes_dashboard.core.spool_warmup_scheduler import init_warmup_scheduler
            init_warmup_scheduler(app)  # Start spool warmup scheduler (leader-elected)
            from mes_dashboard.core.metrics_history import start_metrics_history
            start_metrics_history(app)  # Start metrics history collector
            from mes_dashboard.core.worker_memory_guard import start_worker_memory_guard
            start_worker_memory_guard()  # Start RSS memory guard
            from mes_dashboard.core.login_session_store import get_login_session_store
            get_login_session_store()  # Initialize LoginSessionStore
            # MySQL dual-layer sync (optional, controlled by MYSQL_OPS_ENABLED)
            from mes_dashboard.core.mysql_client import MYSQL_OPS_ENABLED
            if MYSQL_OPS_ENABLED:
                try:
                    from mes_dashboard.core.mysql_client import get_mysql_engine
                    get_mysql_engine()  # Initialise engine (validates connection config)
                    from mes_dashboard.core.sync_worker import start_sync_worker
                    start_sync_worker()
                except Exception as _mysql_exc:
                    logging.getLogger("mes_dashboard").warning(
                        "MySQL OPS init failed (system continues in SQLite-only mode): %s",
                        _mysql_exc,
                    )
    # Store a module-level reference so _start_per_worker_services() (called
    # from post_fork with no app argument) can pass the correct Flask app to
    # services that require an app context.
    global _APP_INSTANCE
    _APP_INSTANCE = app

    _register_shutdown_hooks(app)

    # Import job service modules so their module-level register_job_type() side
    # effects run at app startup.  The downtime job service must be imported here
    # (not lazily inside a route handler) so that register_job_type("downtime",...)
    # fires before any request is handled (IP-3 / design.md D6 / AC-7a).
    import mes_dashboard.services.downtime_query_job_service  # noqa: F401
    import mes_dashboard.services.hold_query_job_service  # noqa: F401
    import mes_dashboard.services.resource_query_job_service  # noqa: F401
    import mes_dashboard.workers.eap_alarm_worker  # noqa: F401

    # Register API routes
    register_routes(app)

    # Register auth, admin, and health routes
    app.register_blueprint(user_auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)

    # Layer 1 gate for /internal/metrics: only testing / nightly / soak
    # configs set REGISTER_INTERNAL_METRICS=True.  Production config leaves
    # it False so the module is never even imported and the URL rule never
    # enters the map — see openspec harden-real-infra-test-coverage spec 3.1.
    if app.config.get("REGISTER_INTERNAL_METRICS"):
        from mes_dashboard.routes.internal_routes import internal_bp
        app.register_blueprint(internal_bp)

    # ========================================================
    # Permission Middleware
    # ========================================================

    @app.before_request
    def check_page_access():
        """Check page access permissions before each request."""
        # Skip static files
        if request.endpoint == "static":
            return None

        # Health check endpoint - no auth required
        if request.path == "/health":
            return None

        # API endpoints check
        if request.path.startswith("/api/"):
            # Auth endpoints are always public
            if request.path.startswith("/api/auth/"):
                return None
            if is_api_public():
                return None
            if not is_user_logged_in():
                from mes_dashboard.core.response import unauthorized_error
                return unauthorized_error()
            return None

        # Admin pages require admin login
        if request.path.startswith("/admin/"):
            if not is_admin_logged_in():
                if _is_ajax_request():
                    return jsonify({"error": "請先登入管理員帳號", "login_required": True}), 401
                return redirect(url_for("portal_shell_page"))
            return None

        # Check page status for registered pages only
        # Unregistered pages pass through to Flask routing (may return 404)
        page_status = get_page_status(request.path)
        if page_status == "dev" and not is_admin_logged_in():
            return render_template("403.html"), 403

        return None

    @app.before_request
    def enforce_csrf():
        if not should_enforce_csrf(
            request,
            enabled=bool(app.config.get("CSRF_ENABLED", True)),
        ):
            return None

        if validate_csrf(request):
            return None

        if request.path == "/admin/login":
            return render_template("login.html", error="CSRF 驗證失敗，請重新提交"), 403

        from mes_dashboard.core.response import error_response, FORBIDDEN

        return error_response(
            FORBIDDEN,
            "CSRF 驗證失敗",
            status_code=403,
        )

    @app.after_request
    def apply_security_headers(response):
        request_is_secure = _is_request_secure(app)
        for header, value in security_headers.items():
            response.headers.setdefault(header, value)
        if is_production and request_is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        else:
            response.headers.pop("Strict-Transport-Security", None)
        # CORS: 僅在明確設定允許來源時加入標頭（同源架構保持不加）
        if _cors_allowed_origins:
            origin = request.headers.get("Origin", "")
            if origin in _cors_allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"
                if request.method == "OPTIONS":
                    response.headers["Access-Control-Allow-Methods"] = (
                        "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                    )
                    response.headers["Access-Control-Allow-Headers"] = (
                        "Content-Type, Authorization, X-CSRFToken"
                    )
                    response.headers["Access-Control-Max-Age"] = "86400"
        _normalize_session_cookie_security(
            response,
            secure=request_is_secure,
            session_cookie_name=str(app.config.get("SESSION_COOKIE_NAME", "session")),
        )
        return response

    # ========================================================
    # Template Context Processor
    # ========================================================

    @app.context_processor
    def inject_admin():
        """Inject admin info into all templates."""
        admin = is_admin_logged_in()

        def can_view_page(route: str) -> bool:
            """Check if current user can view a page."""
            status = get_page_status(route)
            # Unregistered pages (None) are viewable
            if status is None:
                return True
            # Released pages are viewable by all
            if status == "released":
                return True
            # Dev pages only viewable by admin
            return admin

        def frontend_asset(filename: str) -> str | None:
            """Resolve frontend asset path served from static/dist."""
            if not filename:
                return None
            return url_for("static", filename=f"dist/{filename}")

        return {
            "is_admin": admin,
            "admin_user": session.get("user"),
            "can_view_page": can_view_page,
            "frontend_asset": frontend_asset,
            "csrf_token": get_csrf_token,
            "portal_spa_enabled": bool(app.config.get("PORTAL_SPA_ENABLED", False)),
        }

    # ========================================================
    # Page Routes
    # ========================================================

    @app.route('/')
    def portal_index():
        """Portal home with tabs."""
        if bool(app.config.get("PORTAL_SPA_ENABLED", False)):
            return redirect(url_for("portal_shell_page"))
        return render_template('portal.html', drawers=get_navigation_config())

    @app.route('/portal-shell')
    @app.route('/portal-shell/')
    @app.route('/portal-shell/<path:_subpath>')
    def portal_shell_page(_subpath: str | None = None):
        """Portal SPA shell page served as pure Vite HTML output."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "portal-shell.html")
        shell_logger = logging.getLogger("mes_dashboard.portal_shell")

        def _inject_csrf(html: str) -> str:
            csrf_meta = f'<meta name="csrf-token" content="{get_csrf_token()}">'
            return html.replace("<meta charset", f"{csrf_meta}\n    <meta charset", 1)

        def _try_read_shell_html(path: str) -> str | None:
            if not os.path.exists(path):
                return None
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except OSError as exc:
                shell_logger.warning("Failed reading portal shell html: path=%s error=%s", path, exc)
                return None

        html = _try_read_shell_html(dist_html)
        if html is not None:
            return _inject_csrf(html), 200, {"Content-Type": "text/html; charset=utf-8"}

        nested_dist_dir = os.path.join(dist_dir, "src", "portal-shell")
        nested_dist_html = os.path.join(nested_dist_dir, "index.html")
        html = _try_read_shell_html(nested_dist_html)
        if html is not None:
            return _inject_csrf(html), 200, {"Content-Type": "text/html; charset=utf-8"}

        return (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            f"<meta name=\"csrf-token\" content=\"{get_csrf_token()}\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>MES Portal Shell</title>"
            "<link rel=\"stylesheet\" href=\"/static/dist/tailwind.css\">"
            "<link rel=\"stylesheet\" href=\"/static/dist/portal-shell.css\">"
            "<script type=\"module\" src=\"/static/dist/portal-shell.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        )

    @app.route('/api/portal/navigation', methods=['GET'])
    def portal_navigation_config():
        """Return effective drawer/page navigation config for current user."""
        nav_logger = logging.getLogger("mes_dashboard.portal_navigation")
        admin = is_admin_logged_in()
        admin_user_payload = None
        if is_user_logged_in():
            raw_user = session.get("user") or {}
            admin_user_payload = {
                "displayName": raw_user.get("displayName"),
                "username": raw_user.get("username"),
                "mail": raw_user.get("mail"),
                "department": raw_user.get("department"),
            }
        source = get_navigation_config()
        drawers: list[dict] = []
        shell_contract_routes = _load_shell_route_contract_routes()
        deferred_routes = _load_shell_deferred_routes()
        diagnostics: dict[str, object] = {
            "filtered_drawers": 0,
            "filtered_pages": 0,
            "invalid_drawers": 0,
            "invalid_pages": 0,
            "contract_mismatch_routes": [],
        }
        mismatch_routes: set[str] = set()

        for drawer_index, drawer in enumerate(source):
            drawer_id = str(drawer.get("id") or "").strip()
            if not drawer_id:
                diagnostics["invalid_drawers"] = int(diagnostics["invalid_drawers"]) + 1
                nav_logger.warning(
                    "Skipping navigation drawer with missing id at index=%s",
                    drawer_index,
                )
                continue

            admin_only = bool(drawer.get("admin_only", False))
            if admin_only and not admin:
                diagnostics["filtered_drawers"] = int(diagnostics["filtered_drawers"]) + 1
                continue

            raw_pages = drawer.get("pages", [])
            if not isinstance(raw_pages, list):
                diagnostics["invalid_drawers"] = int(diagnostics["invalid_drawers"]) + 1
                nav_logger.warning(
                    "Skipping navigation drawer with invalid pages payload: drawer_id=%s type=%s",
                    drawer_id,
                    type(raw_pages).__name__,
                )
                continue

            pages: list[dict] = []
            for page_index, page in enumerate(raw_pages):
                if not isinstance(page, dict):
                    diagnostics["invalid_pages"] = int(diagnostics["invalid_pages"]) + 1
                    nav_logger.warning(
                        "Skipping invalid page payload under drawer_id=%s index=%s type=%s",
                        drawer_id,
                        page_index,
                        type(page).__name__,
                    )
                    continue

                route = str(page.get("route") or "").strip()
                if not route or not route.startswith("/"):
                    diagnostics["invalid_pages"] = int(diagnostics["invalid_pages"]) + 1
                    nav_logger.warning(
                        "Skipping page with invalid route: drawer_id=%s route=%s",
                        drawer_id,
                        route,
                    )
                    continue

                if not _can_view_page_for_user(route, is_admin=admin):
                    diagnostics["filtered_pages"] = int(diagnostics["filtered_pages"]) + 1
                    continue

                if shell_contract_routes and route not in shell_contract_routes and route not in deferred_routes:
                    mismatch_routes.add(route)
                    nav_logger.warning(
                        "Navigation route missing shell contract: drawer_id=%s route=%s",
                        drawer_id,
                        route,
                    )

                pages.append(
                    {
                        "route": route,
                        "name": page.get("name") or route,
                        "status": page.get("status", "dev"),
                        "order": _safe_order(page.get("order")),
                    }
                )

            if not pages:
                continue
            pages = sorted(
                pages,
                key=lambda p: (_safe_order(p.get("order")), str(p.get("name") or p.get("route") or "")),
            )

            drawers.append(
                {
                    "id": drawer_id,
                    "name": drawer.get("name"),
                    "order": _safe_order(drawer.get("order")),
                    "admin_only": admin_only,
                    "pages": pages,
                }
            )
        drawers = sorted(
            drawers,
            key=lambda d: (_safe_order(d.get("order")), str(d.get("name") or d.get("id") or "")),
        )
        diagnostics["contract_mismatch_routes"] = sorted(mismatch_routes)

        _ai_enabled = os.getenv("AI_QUERY_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        return jsonify(
            {
                "drawers": drawers,
                "is_admin": admin,
                "admin_user": admin_user_payload,
                "admin_links": {
                    "logout": "/api/auth/logout" if admin else None,
                    "pages": "/admin/pages" if admin else None,
                    "dashboard": "/admin/dashboard" if admin else None,
                    "performance": "/admin/performance" if admin else None,
                },
                "diagnostics": diagnostics,
                "portal_spa_enabled": bool(app.config.get("PORTAL_SPA_ENABLED", False)),
                "features": {
                    "ai_query_enabled": _ai_enabled,
                },
            }
        )

    @app.route('/favicon.ico')
    def favicon():
        """Serve favicon without 404 noise."""
        return redirect(url_for('static', filename='favicon.svg'), code=302)

    @app.route('/wip-overview')
    def wip_overview_page():
        """WIP Overview Dashboard served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/wip-overview')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "wip-overview.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'wip-overview.html')

        # Test/local fallback when frontend build artifacts are absent.
        return missing_in_scope_asset_response('/wip-overview', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>WIP Overview Dashboard</title>"
            "<script type=\"module\" src=\"/static/dist/wip-overview.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/wip-detail')
    def wip_detail_page():
        """WIP Detail Dashboard served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/wip-detail')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "wip-detail.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'wip-detail.html')

        # Test/local fallback when frontend build artifacts are absent.
        return missing_in_scope_asset_response('/wip-detail', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>WIP Detail Dashboard</title>"
            "<script type=\"module\" src=\"/static/dist/wip-detail.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/resource')
    def resource_page():
        """Resource status report page served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/resource')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "resource-status.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'resource-status.html')

        # Test/local fallback when frontend build artifacts are absent.
        return missing_in_scope_asset_response('/resource', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>設備即時概況</title>"
            "<script type=\"module\" src=\"/static/dist/resource-status.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/resource-history')
    def resource_history_page():
        """Resource history analysis page served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/resource-history')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "resource-history.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'resource-history.html')

        # Test/local fallback when frontend build artifacts are absent.
        return missing_in_scope_asset_response('/resource-history', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>設備歷史績效</title>"
            "<script type=\"module\" src=\"/static/dist/resource-history.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/reject-history')
    def reject_history_page():
        """Reject history analysis page served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/reject-history')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "reject-history.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'reject-history.html')

        return missing_in_scope_asset_response('/reject-history', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>報廢歷史查詢</title>"
            "<script type=\"module\" src=\"/static/dist/reject-history.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/yield-alert-center')
    def yield_alert_center_page():
        """Yield alert center page served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/yield-alert-center')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "yield-alert-center.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'yield-alert-center.html')

        nested_dist_dir = os.path.join(dist_dir, "src", "yield-alert-center")
        nested_dist_html = os.path.join(nested_dist_dir, "index.html")
        if os.path.exists(nested_dist_html):
            return send_from_directory(nested_dist_dir, "index.html")

        return missing_in_scope_asset_response('/yield-alert-center', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>良率查詢</title>"
            "<script type=\"module\" src=\"/static/dist/yield-alert-center.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/qc-gate')
    def qc_gate_page():
        """QC-GATE status report served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/qc-gate')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "qc-gate.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'qc-gate.html')

        return missing_in_scope_asset_response('/qc-gate', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>QC-GATE 狀態</title>"
            "<script type=\"module\" src=\"/static/dist/qc-gate.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/mid-section-defect')
    def mid_section_defect_page():
        """Mid-section defect traceability analysis page (pure Vite)."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/mid-section-defect')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "mid-section-defect.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'mid-section-defect.html')

        return missing_in_scope_asset_response('/mid-section-defect', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>中段製程不良追溯</title>"
            "<script type=\"module\" src=\"/static/dist/mid-section-defect.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/material-trace')
    def material_trace_page():
        """Material trace query page served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/material-trace')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "material-trace.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'material-trace.html')

        return missing_in_scope_asset_response('/material-trace', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>原物料追溯查詢</title>"
            "<script type=\"module\" src=\"/static/dist/material-trace.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    @app.route('/eap-alarm')
    def eap_alarm_page():
        """EAP ALARM analysis page served as pure Vite HTML output."""
        canonical_redirect = maybe_redirect_to_canonical_shell('/eap-alarm')
        if canonical_redirect is not None:
            return canonical_redirect

        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "eap-alarm.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'eap-alarm.html')

        return missing_in_scope_asset_response('/eap-alarm', (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>EAP ALARM 分析</title>"
            "<script type=\"module\" src=\"/static/dist/eap-alarm.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        ))

    # ========================================================
    # Table Query APIs (for table_data_viewer)
    # ========================================================

    from mes_dashboard.config.tables import TABLES_CONFIG

    _ALLOWED_TABLES: dict[str, dict] = {}
    for _tables in TABLES_CONFIG.values():
        for _tbl in _tables:
            _ALLOWED_TABLES[_tbl['name']] = _tbl

    def _validate_table_request(table_name, time_field=None):
        """Validate table_name against TABLES_CONFIG whitelist."""
        if not table_name:
            return '請指定表名', 400
        if table_name not in _ALLOWED_TABLES:
            return '不允許查詢此表', 400
        if time_field is not None:
            allowed_time = _ALLOWED_TABLES[table_name].get('time_field')
            if time_field != allowed_time:
                return '不允許的時間欄位', 400
        return None, None

    @app.route('/api/query_table', methods=['POST'])
    def query_table():
        """API: query table data with optional column filters."""
        data = request.get_json()
        table_name = data.get('table_name')
        limit = data.get('limit', 1000)
        time_field = data.get('time_field')
        filters = data.get('filters')

        error, status = _validate_table_request(table_name, time_field)
        if error:
            return jsonify({'error': error}), status

        result = get_table_data(table_name, limit, time_field, filters)
        return jsonify(result)

    @app.route('/api/get_table_columns', methods=['POST'])
    def api_get_table_columns():
        """API: get column names for a table."""
        data = request.get_json()
        table_name = data.get('table_name')

        error, status = _validate_table_request(table_name)
        if error:
            return jsonify({'error': error}), status

        columns = get_table_columns(table_name)
        return jsonify({'columns': columns})

    @app.route('/api/get_table_info', methods=['GET'])
    def get_table_info():
        """API: get tables config."""
        from mes_dashboard.config.tables import TABLES_CONFIG

        return jsonify(TABLES_CONFIG)

    # ========================================================
    # Global Error Handlers
    # ========================================================
    _register_error_handlers(app)

    return app


def _register_error_handlers(app: Flask) -> None:
    """Register global error handlers with standardized response format."""
    from mes_dashboard.core.response import (
        unauthorized_error,
        forbidden_error,
        not_found_error,
        internal_error,
        db_connection_error,
        db_query_timeout_error,
        db_query_error,
        pool_exhausted_error,
        error_response,
        INTERNAL_ERROR
    )
    from mes_dashboard.core.database import (
        DatabasePoolExhaustedError,
        DatabaseCircuitOpenError,
        _extract_ora_code,
    )
    import oracledb
    from mes_dashboard.core.response import circuit_breaker_error

    @app.errorhandler(401)
    def handle_unauthorized(e):
        """Handle 401 Unauthorized errors."""
        return unauthorized_error()

    @app.errorhandler(403)
    def handle_forbidden(e):
        """Handle 403 Forbidden errors."""
        return forbidden_error()

    @app.errorhandler(404)
    def handle_not_found(e):
        """Handle 404 Not Found errors."""
        # For API routes, return JSON; for pages, render template
        if request.path.startswith('/api/'):
            return not_found_error()
        return render_template('404.html'), 404

    def _is_api_request() -> bool:
        """Check if the current request is an API request."""
        return (request.path.startswith('/api/') or
                '/api/' in request.path or
                request.accept_mimetypes.best == 'application/json')

    @app.errorhandler(500)
    def handle_internal_error(e):
        """Handle 500 Internal Server errors."""
        logger = logging.getLogger('mes_dashboard')
        logger.error(f"Internal server error: {e}", exc_info=True)
        if _is_api_request():
            return internal_error(str(e) if app.debug else None)
        # Fallback to HTML template for non-API requests.
        try:
            return render_template('500.html'), 500
        except Exception:
            return internal_error(str(e) if app.debug else None)

    @app.errorhandler(DatabasePoolExhaustedError)
    def handle_pool_exhausted(e: DatabasePoolExhaustedError):
        """Handle DB pool exhaustion with degraded response contract."""
        retry_after = max(int(getattr(e, "retry_after_seconds", 5)), 1)
        return pool_exhausted_error(
            str(e) if app.debug else None,
            retry_after_seconds=retry_after,
        )

    @app.errorhandler(DatabaseCircuitOpenError)
    def handle_circuit_open(e: DatabaseCircuitOpenError):
        """Handle circuit-open condition with degraded response contract."""
        retry_after = max(int(getattr(e, "retry_after_seconds", 30)), 1)
        return circuit_breaker_error(
            str(e) if app.debug else None,
            retry_after_seconds=retry_after,
        )

    @app.errorhandler(oracledb.DatabaseError)
    def handle_oracle_database_error(e: oracledb.DatabaseError):
        """Handle Oracle driver exceptions with ORA-code-aware contracts."""
        logger = logging.getLogger('mes_dashboard')
        ora_code = _extract_ora_code(e)
        details = str(e) if app.debug else None

        # ORA-00028: session killed — connection-layer event, client should retry
        retryable_connection_codes = {"12514", "12541", "03113", "03135", "00028"}
        if ora_code == "01017":
            logger.warning("Oracle auth/connection configuration error (ORA-%s)", ora_code)
            return db_connection_error(details)
        if ora_code in retryable_connection_codes:
            logger.warning("Oracle transient connectivity error (ORA-%s)", ora_code)
            return db_connection_error(details, retry_after_seconds=30)
        if ora_code == "01555":
            logger.warning("Oracle snapshot-too-old error (ORA-%s)", ora_code)
            return db_query_timeout_error(details)

        logger.error("Unmapped Oracle database error (ORA-%s)", ora_code, exc_info=True)
        return db_query_error(details)

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle uncaught exceptions."""
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException):
            return e
        logger = logging.getLogger('mes_dashboard')
        logger.error(f"Uncaught exception: {e}", exc_info=True)
        if _is_api_request():
            return error_response(
                INTERNAL_ERROR,
                "伺服器發生未預期的錯誤",
                str(e) if app.debug else None,
                status_code=500
            )
        # Fallback to JSON if template not found
        try:
            return render_template('500.html'), 500
        except Exception:
            return error_response(
                INTERNAL_ERROR,
                "伺服器發生未預期的錯誤",
                str(e) if app.debug else None,
                status_code=500
            )
