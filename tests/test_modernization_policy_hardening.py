# -*- coding: utf-8 -*-
"""Hardening tests for modernization policy caching behavior."""

from __future__ import annotations

import json

from mes_dashboard.core import modernization_policy as policy


def test_scope_matrix_loader_returns_defensive_copy(tmp_path, monkeypatch):
    scope_file = tmp_path / "route_scope_matrix.json"
    scope_file.write_text(
        json.dumps({"in_scope": [{"route": "/wip-overview"}], "deferred": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(policy, "SCOPE_MATRIX_FILE", scope_file)
    policy.clear_modernization_policy_cache()

    payload = policy.load_scope_matrix()
    payload["in_scope"].append({"route": "/mutated"})

    fresh_payload = policy.load_scope_matrix()
    routes = [item["route"] for item in fresh_payload["in_scope"]]
    assert routes == ["/wip-overview"]


def test_scope_matrix_cache_refresh_requires_explicit_clear(tmp_path, monkeypatch):
    scope_file = tmp_path / "route_scope_matrix.json"
    scope_file.write_text(
        json.dumps({"in_scope": [{"route": "/before"}], "deferred": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(policy, "SCOPE_MATRIX_FILE", scope_file)
    policy.clear_modernization_policy_cache()
    assert [item["route"] for item in policy.load_scope_matrix()["in_scope"]] == ["/before"]

    scope_file.write_text(
        json.dumps({"in_scope": [{"route": "/after"}], "deferred": []}),
        encoding="utf-8",
    )
    assert [item["route"] for item in policy.load_scope_matrix()["in_scope"]] == ["/before"]

    policy.clear_modernization_policy_cache()
    assert [item["route"] for item in policy.load_scope_matrix()["in_scope"]] == ["/after"]
