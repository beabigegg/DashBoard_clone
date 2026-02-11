import unittest
import os

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
            "/tables",
            "/resource",
            "/wip-overview",
            "/wip-detail",
            "/hold-overview",
            "/excel-query",
            "/query-tool",
            "/tmtt-defect",
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
            "/api/excel-query/upload",
            "/api/query-tool/resolve",
            "/api/tmtt-defect/analysis",
        }
        missing = expected - rules
        self.assertFalse(missing, f"Missing routes: {sorted(missing)}")

    def test_portal_spa_flag_default_enabled(self):
        old = os.environ.pop("PORTAL_SPA_ENABLED", None)
        try:
            app = create_app("testing")
            self.assertTrue(app.config.get("PORTAL_SPA_ENABLED"))

            client = app.test_client()
            response = client.get("/", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers.get("Location"), "/portal-shell")
        finally:
            if old is not None:
                os.environ["PORTAL_SPA_ENABLED"] = old

    def test_portal_spa_flag_disabled_via_env(self):
        old = os.environ.get("PORTAL_SPA_ENABLED")
        os.environ["PORTAL_SPA_ENABLED"] = "false"
        try:
            app = create_app("testing")
            self.assertFalse(app.config.get("PORTAL_SPA_ENABLED"))

            client = app.test_client()
            response = client.get("/")
            html = response.data.decode("utf-8")
            self.assertIn('data-portal-spa-enabled="false"', html)
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
            self.assertEqual(response.headers.get("Location"), "/portal-shell")
        finally:
            if old is None:
                os.environ.pop("PORTAL_SPA_ENABLED", None)
            else:
                os.environ["PORTAL_SPA_ENABLED"] = old


if __name__ == "__main__":
    unittest.main()
