import unittest
import os
import sys
from unittest import mock

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class AppFactoryTests(unittest.TestCase):
    def setUp(self):
        db._ENGINE = None

    def test_create_app_default_config(self):
        app = create_app("development")
        self.assertTrue(app.config.get("DEBUG"))
        self.assertEqual(app.config.get("ENV"), "development")
        cache = app.extensions.get("cache")
        self.assertIsNotNone(cache)
        cache.set("app_factory_probe", {"ok": True}, 30)
        self.assertEqual(cache.get("app_factory_probe"), {"ok": True})

    def test_create_app_production_config(self):
        old_secret = os.environ.get("SECRET_KEY")
        old_conda_env_name = os.environ.get("CONDA_ENV_NAME")
        try:
            os.environ["SECRET_KEY"] = "test-production-secret-key"
            # Keep runtime-contract strict validation aligned with active env.
            os.environ["CONDA_ENV_NAME"] = os.environ.get("CONDA_DEFAULT_ENV", "base")
            app = create_app("production")
            self.assertFalse(app.config.get("DEBUG"))
            self.assertEqual(app.config.get("ENV"), "production")
        finally:
            if old_secret is None:
                os.environ.pop("SECRET_KEY", None)
            else:
                os.environ["SECRET_KEY"] = old_secret
            if old_conda_env_name is None:
                os.environ.pop("CONDA_ENV_NAME", None)
            else:
                os.environ["CONDA_ENV_NAME"] = old_conda_env_name

    def test_create_app_independent_instances(self):
        app1 = create_app("development")
        db._ENGINE = None
        app2 = create_app("development")
        self.assertIsNot(app1, app2)

    def test_routes_registered(self):
        app = create_app("development")
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        expected = {
            "/",
            "/portal-shell",
            "/resource",
            "/wip-overview",
            "/wip-detail",
            "/hold-overview",
            "/reject-history",
            "/yield-alert-center",
            "/query-tool",
            "/api/wip/overview/summary",
            "/api/wip/overview/matrix",
            "/api/wip/overview/hold",
            "/api/hold-overview/summary",
            "/api/hold-overview/matrix",
            "/api/hold-overview/treemap",
            "/api/hold-overview/lots",
            "/api/wip/detail/<workcenter>",
            "/api/wip/meta/workcenters",
            "/api/wip/meta/packages",
            "/api/resource/status/summary",
            "/api/dashboard/kpi",
            "/api/portal/navigation",
            "/api/query-tool/resolve",
            "/api/reject-history/summary",
            "/api/yield-alert/summary",
        }
        missing = expected - rules
        self.assertFalse(missing, f"Missing routes: {sorted(missing)}")

        # Route-name pin: '/' must be registered under the name 'portal_index'.
        rule_names = {rule.endpoint: rule.rule for rule in app.url_map.iter_rules()}
        self.assertIn("portal_index", rule_names, "'portal_index' route name must be registered")
        self.assertEqual(rule_names["portal_index"], "/", "portal_index must map to '/'")

        # portal_index must always redirect to the SPA shell regardless of PORTAL_SPA_ENABLED.
        for flag_val in ("true", "false"):
            old_flag = os.environ.get("PORTAL_SPA_ENABLED")
            os.environ["PORTAL_SPA_ENABLED"] = flag_val
            db._ENGINE = None
            flag_app = create_app("testing")
            flag_client = flag_app.test_client()
            with flag_app.test_request_context():
                with flag_client.session_transaction() as sess:
                    sess["user"] = {"username": "A001", "displayName": "Test", "mail": "t@t.com", "is_admin": False}
            resp = flag_client.get("/", follow_redirects=False)
            self.assertEqual(
                resp.status_code, 302,
                f"portal_index must redirect (302) when PORTAL_SPA_ENABLED={flag_val}",
            )
            self.assertIn(
                "/portal-shell",
                resp.headers.get("Location", ""),
                f"portal_index must redirect to /portal-shell when PORTAL_SPA_ENABLED={flag_val}",
            )
            if old_flag is None:
                os.environ.pop("PORTAL_SPA_ENABLED", None)
            else:
                os.environ["PORTAL_SPA_ENABLED"] = old_flag
            db._ENGINE = None

    def test_portal_spa_flag_default_enabled(self):
        old = os.environ.pop("PORTAL_SPA_ENABLED", None)
        try:
            app = create_app("testing")
            self.assertTrue(app.config.get("PORTAL_SPA_ENABLED"))

            client = app.test_client()
            response = client.get("/", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("Location", "")
            self.assertTrue(location.startswith("/portal-shell"))
        finally:
            if old is not None:
                os.environ["PORTAL_SPA_ENABLED"] = old

    def test_portal_spa_flag_disabled_via_env(self):
        old = os.environ.get("PORTAL_SPA_ENABLED")
        os.environ["PORTAL_SPA_ENABLED"] = "false"
        try:
            app = create_app("testing")
            # Flag resolution: app.config must reflect the env override.
            self.assertFalse(app.config.get("PORTAL_SPA_ENABLED"))

            # Behavioral assertion: portal_index always redirects to the SPA
            # shell even when PORTAL_SPA_ENABLED is false (non-SPA render path
            # has been removed; portal.html no longer exists).
            client = app.test_client()
            response = client.get("/", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("Location", "")
            self.assertTrue(
                location.startswith("/portal-shell"),
                f"portal_index must redirect to /portal-shell even when flag=false; got {location}",
            )
        finally:
            if old is None:
                os.environ.pop("PORTAL_SPA_ENABLED", None)
            else:
                os.environ["PORTAL_SPA_ENABLED"] = old

    def test_portal_spa_flag_enabled_via_env(self):
        old = os.environ.get("PORTAL_SPA_ENABLED")
        os.environ["PORTAL_SPA_ENABLED"] = "true"
        try:
            app = create_app("testing")
            self.assertTrue(app.config.get("PORTAL_SPA_ENABLED"))

            client = app.test_client()
            response = client.get("/", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            location = response.headers.get("Location", "")
            self.assertTrue(location.startswith("/portal-shell"))
        finally:
            if old is None:
                os.environ.pop("PORTAL_SPA_ENABLED", None)
            else:
                os.environ["PORTAL_SPA_ENABLED"] = old

    def test_default_env_is_production_when_flask_env_missing(self):
        old_flask_env = os.environ.pop("FLASK_ENV", None)
        old_secret = os.environ.get("SECRET_KEY")
        old_runtime_contract = os.environ.get("RUNTIME_CONTRACT_ENFORCE")
        old_realtime_cache = os.environ.get("REALTIME_EQUIPMENT_CACHE_ENABLED")
        try:
            os.environ["SECRET_KEY"] = "test-production-secret-key"
            os.environ["RUNTIME_CONTRACT_ENFORCE"] = "false"
            os.environ["REALTIME_EQUIPMENT_CACHE_ENABLED"] = "false"

            app = create_app()
            self.assertEqual(app.config.get("ENV"), "production")
        finally:
            if old_flask_env is not None:
                os.environ["FLASK_ENV"] = old_flask_env
            if old_secret is None:
                os.environ.pop("SECRET_KEY", None)
            else:
                os.environ["SECRET_KEY"] = old_secret
            if old_runtime_contract is None:
                os.environ.pop("RUNTIME_CONTRACT_ENFORCE", None)
            else:
                os.environ["RUNTIME_CONTRACT_ENFORCE"] = old_runtime_contract
            if old_realtime_cache is None:
                os.environ.pop("REALTIME_EQUIPMENT_CACHE_ENABLED", None)
            else:
                os.environ["REALTIME_EQUIPMENT_CACHE_ENABLED"] = old_realtime_cache


def test_status_payload_exposes_portal_spa_enabled():
    """Template context processor must still inject portal_spa_enabled (AC-5).

    The flag is preserved in app.config even after the non-SPA render path is
    removed; the context processor at app.py:1048 must keep exposing it so that
    any remaining Jinja2 templates (admin, error pages) can reference it.
    """
    import mes_dashboard.core.database as _db
    _db._ENGINE = None
    app = create_app("testing")
    ctx_processor_result = None
    # The context processor calls is_admin_logged_in() which reads session,
    # so we need a real request context with a minimal user session.
    with app.test_request_context("/"):
        with app.test_client().session_transaction() as sess:
            pass  # establish session fixture via request context
        from flask import session as flask_session
        flask_session["user"] = {"username": "A001", "is_admin": False}
        for processor in app.template_context_processors[None]:
            try:
                result = processor()
                if isinstance(result, dict) and "portal_spa_enabled" in result:
                    ctx_processor_result = result
                    break
            except Exception:
                continue
    assert ctx_processor_result is not None, (
        "No template context processor exposes 'portal_spa_enabled'; "
        "app.py context processor may have been removed"
    )
    assert "portal_spa_enabled" in ctx_processor_result, (
        "portal_spa_enabled key missing from template context processor payload"
    )


def test_portal_html_template_deleted():
    """templates/portal.html must not exist (AC-6: deliberate delete)."""
    import pathlib
    templates_dir = pathlib.Path(__file__).parent.parent / "src" / "mes_dashboard" / "templates"
    portal_html = templates_dir / "portal.html"
    assert not portal_html.exists(), (
        f"templates/portal.html still exists at {portal_html}; "
        "it should have been deleted as part of the legacy-portal-admin-cleanup change"
    )


def test_no_portal_html_reference_in_app_source():
    """No source file under src/mes_dashboard/ should reference 'portal.html' (AC-6).

    Uses ast.parse() + ast.walk() on every .py file to assert the string constant
    'portal.html' does not appear in any AST Constant node (per test-discipline.md
    §Use ast.parse() to Prove Absence of Removed Startup Calls).
    """
    import ast
    import pathlib
    src_root = pathlib.Path(__file__).parent.parent / "src" / "mes_dashboard"
    violations = []
    for py_file in src_root.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if "portal.html" in node.value:
                    violations.append(f"{py_file}:{node.lineno}: {node.value!r}")
    assert not violations, (
        "Found 'portal.html' string in source files — re-introduction detected:\n"
        + "\n".join(violations)
    )


class PostForkHookTests(unittest.TestCase):
    """Tests for the preload_app + post_fork architecture (IP-3, IP-6)."""

    def test_post_fork_hook_registered_in_gunicorn_conf(self):
        """gunicorn.conf.py must define a callable named post_fork (AC-5).

        gunicorn auto-detects hook functions by name (like on_starting / worker_exit).
        This test imports gunicorn.conf as a module and verifies post_fork exists
        and is callable.
        """
        # Add the repo root to sys.path so we can import gunicorn.conf as a module.
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        original_path = sys.path[:]
        try:
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)

            # Import gunicorn.conf.py as a module.  It may already be cached.
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "gunicorn_conf",
                os.path.join(repo_root, "gunicorn.conf.py"),
            )
            gunicorn_conf = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gunicorn_conf)

            self.assertTrue(
                hasattr(gunicorn_conf, "post_fork"),
                "gunicorn.conf.py must define a post_fork function",
            )
            self.assertTrue(
                callable(gunicorn_conf.post_fork),
                "gunicorn.conf.post_fork must be callable",
            )
        finally:
            sys.path[:] = original_path

    def test_post_fork_hook_callable_in_test_mode_no_crash(self):
        """Calling post_fork with mock server+worker objects must not raise.

        The hook wraps each reinit step in try/except, so even with no real
        Oracle/Redis/SQLite available, it must log warnings and return cleanly.
        """
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gunicorn_conf_callable",
            os.path.join(repo_root, "gunicorn.conf.py"),
        )
        gunicorn_conf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gunicorn_conf)

        mock_server = mock.MagicMock()
        mock_worker = mock.MagicMock()
        # Should not raise regardless of missing Oracle/Redis connections.
        try:
            gunicorn_conf.post_fork(mock_server, mock_worker)
        except Exception as exc:
            self.fail(
                f"post_fork raised an exception — all failures must be caught internally: {exc}"
            )

    def test_start_per_worker_services_does_not_crash_in_test_mode(self):
        """_start_per_worker_services() must return early in FLASK_TESTING mode (AC-5).

        This pins the guard that prevents background threads from starting in
        test processes, which would cause interference with the test suite.
        """
        os.environ["FLASK_TESTING"] = "true"
        try:
            from mes_dashboard.app import _start_per_worker_services
            # Must not raise and must not start any threads.
            alive_before = {t.name for t in __import__("threading").enumerate()}
            _start_per_worker_services()
            alive_after = {t.name for t in __import__("threading").enumerate()}
            # No new daemon threads should be created in test mode.
            # (main thread + any pre-existing threads are excluded)
            new_threads = alive_after - alive_before
            self.assertEqual(
                new_threads, set(),
                f"_start_per_worker_services() spawned threads in test mode: {new_threads}",
            )
        finally:
            os.environ.pop("FLASK_TESTING", None)

    def test_reinit_sqlite_handles_does_not_crash_in_test_mode(self):
        """_reinit_sqlite_handles() must return early when FLASK_TESTING is set (AC-4)."""
        os.environ["FLASK_TESTING"] = "true"
        try:
            from mes_dashboard.app import _reinit_sqlite_handles
            # Should return without raising.
            result = _reinit_sqlite_handles()
            self.assertIsNone(result)
        finally:
            os.environ.pop("FLASK_TESTING", None)

    def test_api_contracts_unchanged_after_preload(self):
        """Smoke test: portal_navigation_config must return status-feed shape (nav-config-to-code).

        Hits /api/portal/navigation (cheap, no Oracle required) and verifies the
        new status-feed shape: {statuses: {...}, is_admin: bool, admin_links, features, diagnostics}.
        The old 'drawers' key is removed; 'statuses' is the new top-level key.
        This endpoint returns a custom dict (not wrapped in success_response).
        """
        app = create_app("testing")
        client = app.test_client()
        response = client.get("/api/portal/navigation")
        self.assertIn(response.status_code, (200, 401, 403),
                      f"Unexpected status {response.status_code}")
        if response.status_code == 200:
            body = response.get_json()
            self.assertIsNotNone(body, "Response body is not JSON")
            # These keys are the documented shape from the new contract (PortalNavigationResponse).
            for key in ("statuses", "is_admin", "admin_links", "features", "diagnostics"):
                self.assertIn(
                    key, body,
                    f"Navigation response missing key '{key}' — API shape has drifted from nav-config-to-code contract",
                )
            # 'drawers' must NOT be present (removed by nav-config-to-code).
            self.assertNotIn(
                "drawers", body,
                "Navigation response still emits 'drawers' — nav-config-to-code inversion not applied",
            )
            # statuses must be a dict (route → released|dev).
            self.assertIsInstance(body["statuses"], dict,
                                  "statuses must be a dict (route → status)")


if __name__ == "__main__":
    unittest.main()
