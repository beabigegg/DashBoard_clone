# -*- coding: utf-8 -*-
"""Tests for rate-limit client identity trust boundary behavior."""

from flask import Flask

from mes_dashboard.core.rate_limit import _client_identifier


def _app() -> Flask:
    return Flask(__name__)


def test_client_identifier_ignores_xff_when_proxy_trust_disabled(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)

    app = _app()
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "1.2.3.4"},
        environ_base={"REMOTE_ADDR": "9.9.9.9"},
    ):
        assert _client_identifier() == "9.9.9.9"


def test_client_identifier_uses_xff_for_trusted_proxy_source(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1")

    app = _app()
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    ):
        assert _client_identifier() == "1.2.3.4"


def test_client_identifier_rejects_untrusted_proxy_source(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.setenv("TRUSTED_PROXY_IPS", "127.0.0.1")

    app = _app()
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "1.2.3.4"},
        environ_base={"REMOTE_ADDR": "10.10.10.10"},
    ):
        assert _client_identifier() == "10.10.10.10"


def test_client_identifier_requires_allowlist_when_proxy_trust_enabled(monkeypatch):
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)

    app = _app()
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "1.2.3.4"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    ):
        assert _client_identifier() == "127.0.0.1"
