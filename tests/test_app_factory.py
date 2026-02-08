import unittest
import os

from mes_dashboard.app import create_app
import mes_dashboard.core.database as db


class AppFactoryTests(unittest.TestCase):
    def setUp(self):
        db._ENGINE = None

    def test_create_app_default_config(self):
        app = create_app()
        self.assertTrue(app.config.get("DEBUG"))
        self.assertEqual(app.config.get("ENV"), "development")
        cache = app.extensions.get("cache")
        self.assertIsNotNone(cache)
        cache.set("app_factory_probe", {"ok": True}, 30)
        self.assertEqual(cache.get("app_factory_probe"), {"ok": True})

    def test_create_app_production_config(self):
        old_secret = os.environ.get("SECRET_KEY")
        try:
            os.environ["SECRET_KEY"] = "test-production-secret-key"
            app = create_app("production")
            self.assertFalse(app.config.get("DEBUG"))
            self.assertEqual(app.config.get("ENV"), "production")
        finally:
            if old_secret is None:
                os.environ.pop("SECRET_KEY", None)
            else:
                os.environ["SECRET_KEY"] = old_secret

    def test_create_app_independent_instances(self):
        app1 = create_app()
        db._ENGINE = None
        app2 = create_app()
        self.assertIsNot(app1, app2)

    def test_routes_registered(self):
        app = create_app()
        rules = {rule.rule for rule in app.url_map.iter_rules()}
        expected = {
            "/",
            "/tables",
            "/resource",
            "/wip-overview",
            "/wip-detail",
            "/excel-query",
            "/api/wip/overview/summary",
            "/api/wip/overview/matrix",
            "/api/wip/overview/hold",
            "/api/wip/detail/<workcenter>",
            "/api/wip/meta/workcenters",
            "/api/wip/meta/packages",
            "/api/resource/status/summary",
            "/api/dashboard/kpi",
            "/api/excel-query/upload",
        }
        missing = expected - rules
        self.assertFalse(missing, f"Missing routes: {sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
