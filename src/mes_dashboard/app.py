# -*- coding: utf-8 -*-
"""Flask application factory for MES Dashboard."""

from __future__ import annotations

import atexit
import logging
import os
import sys
import threading

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
from mes_dashboard.core.permissions import is_admin_logged_in, _is_ajax_request
from mes_dashboard.core.csrf import (
    get_csrf_token,
    should_enforce_csrf,
    validate_csrf,
)
from mes_dashboard.routes import register_routes
from mes_dashboard.routes.auth_routes import auth_bp
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
from mes_dashboard.core.redis_client import close_redis
from mes_dashboard.core.runtime_contract import build_runtime_contract_diagnostics


_SHUTDOWN_LOCK = threading.Lock()
_ATEXIT_REGISTERED = False


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


def _build_security_headers(production: bool) -> dict[str, str]:
    headers = {
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            # Portal embeds same-origin report pages via iframe.
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        ),
        "X-Frame-Options": "SAMEORIGIN",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
    }
    if production:
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return headers


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
    raw = os.getenv("RUNTIME_CONTRACT_ENFORCE")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return _is_production_env(app)


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


def create_app(config_name: str | None = None) -> Flask:
    """Create and configure the Flask app instance."""
    app = Flask(__name__, template_folder="templates")

    config_class = get_config(config_name)
    app.config.from_object(config_class)

    # Session configuration with environment-aware secret validation.
    app.secret_key = _resolve_secret_key(app)
    app.config["SECRET_KEY"] = app.secret_key

    # Session cookie security settings
    # SECURE: Only send cookie over HTTPS in production.
    app.config['SESSION_COOKIE_SECURE'] = _is_production_env(app)
    # HTTPONLY: Prevent JavaScript access to session cookie (XSS protection)
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    # SAMESITE: strict in production, relaxed for local development usability.
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict' if _is_production_env(app) else 'Lax'

    # Configure logging first
    _configure_logging(app)
    _validate_runtime_contract(app)
    security_headers = _build_security_headers(_is_production_env(app))

    # Route-level cache backend (L1 memory + optional L2 Redis)
    app.extensions["cache"] = create_default_cache_backend()

    # Initialize database teardown and pool
    init_db(app)
    running_pytest = bool(os.getenv("PYTEST_CURRENT_TEST"))
    is_testing_runtime = bool(app.config.get("TESTING")) or app.testing or running_pytest
    with app.app_context():
        if not is_testing_runtime:
            get_engine()
            start_keepalive()  # Keep database connections alive
            start_cache_updater()  # Start Redis cache updater
            init_realtime_equipment_cache(app)  # Start realtime equipment status cache
    _register_shutdown_hooks(app)

    # Register API routes
    register_routes(app)

    # Register auth, admin, and health routes
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(health_bp)

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
            if is_api_public():
                return None
            if not is_admin_logged_in():
                from mes_dashboard.core.response import unauthorized_error
                return unauthorized_error()
            return None

        # Skip auth-related pages (login/logout)
        if request.path.startswith("/admin/login") or request.path.startswith("/admin/logout"):
            return None

        # Admin pages require login
        if request.path.startswith("/admin/"):
            if not is_admin_logged_in():
                # For AJAX requests, return JSON error instead of redirect
                if _is_ajax_request():
                    return jsonify({"error": "請先登入管理員帳號", "login_required": True}), 401
                return redirect(url_for("auth.login", next=request.url))
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
        for header, value in security_headers.items():
            response.headers.setdefault(header, value)
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
            "admin_user": session.get("admin"),
            "can_view_page": can_view_page,
            "frontend_asset": frontend_asset,
            "csrf_token": get_csrf_token,
        }

    # ========================================================
    # Page Routes
    # ========================================================

    @app.route('/')
    def portal_index():
        """Portal home with tabs."""
        return render_template('portal.html', drawers=get_navigation_config())

    @app.route('/favicon.ico')
    def favicon():
        """Serve favicon without 404 noise."""
        return redirect(url_for('static', filename='favicon.svg'), code=302)

    @app.route('/tables')
    def tables_page():
        """Table viewer page served as pure Vite HTML output."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "tables.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'tables.html')

        nested_dist_dir = os.path.join(dist_dir, "src", "tables")
        nested_dist_html = os.path.join(nested_dist_dir, "index.html")
        if os.path.exists(nested_dist_html):
            return send_from_directory(nested_dist_dir, "index.html")

        # Test/local fallback when frontend build artifacts are absent.
        return (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>MES 數據表查詢工具</title>"
            "<script type=\"module\" src=\"/static/dist/tables.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        )

    @app.route('/wip-overview')
    def wip_overview_page():
        """WIP Overview Dashboard served as pure Vite HTML output."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "wip-overview.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'wip-overview.html')

        # Test/local fallback when frontend build artifacts are absent.
        return (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>WIP Overview Dashboard</title>"
            "<script type=\"module\" src=\"/static/dist/wip-overview.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        )

    @app.route('/wip-detail')
    def wip_detail_page():
        """WIP Detail Dashboard served as pure Vite HTML output."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "wip-detail.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'wip-detail.html')

        # Test/local fallback when frontend build artifacts are absent.
        return (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>WIP Detail Dashboard</title>"
            "<script type=\"module\" src=\"/static/dist/wip-detail.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        )

    @app.route('/resource')
    def resource_page():
        """Resource status report page served as pure Vite HTML output."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "resource-status.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'resource-status.html')

        # Test/local fallback when frontend build artifacts are absent.
        return (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>設備即時概況</title>"
            "<script type=\"module\" src=\"/static/dist/resource-status.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        )

    @app.route('/excel-query')
    def excel_query_page():
        """Excel batch query tool page."""
        return render_template('excel_query.html')

    @app.route('/resource-history')
    def resource_history_page():
        """Resource history analysis page served as pure Vite HTML output."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        dist_html = os.path.join(dist_dir, "resource-history.html")
        if os.path.exists(dist_html):
            return send_from_directory(dist_dir, 'resource-history.html')

        # Test/local fallback when frontend build artifacts are absent.
        return (
            "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"UTF-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">"
            "<title>設備歷史績效</title>"
            "<script type=\"module\" src=\"/static/dist/resource-history.js\"></script>"
            "</head><body><div id='app'></div></body></html>",
            200,
        )

    @app.route('/tmtt-defect')
    def tmtt_defect_page():
        """TMTT printing & lead form defect analysis page."""
        return render_template('tmtt_defect.html')

    @app.route('/qc-gate')
    def qc_gate_page():
        """QC-GATE status report served as pure Vite HTML output."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        return send_from_directory(dist_dir, 'qc-gate.html')

    @app.route('/mid-section-defect')
    def mid_section_defect_page():
        """Mid-section defect traceability analysis page (pure Vite)."""
        dist_dir = os.path.join(app.static_folder or "", "dist")
        return send_from_directory(dist_dir, 'mid-section-defect.html')

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
        pool_exhausted_error,
        error_response,
        INTERNAL_ERROR
    )
    from mes_dashboard.core.database import (
        DatabasePoolExhaustedError,
        DatabaseCircuitOpenError,
    )
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

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle uncaught exceptions."""
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
