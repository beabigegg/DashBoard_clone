# -*- coding: utf-8 -*-
"""Oracle XE + toxiproxy pytest fixtures for real-driver fault injection tests.

Provides two fixtures (registered into conftest.py via explicit import):

  oracle_xe       (session-scoped)
    - Polls Oracle XE until ready (max ORACLE_READINESS_TIMEOUT_S).
    - Creates the Oracle proxy entry in toxiproxy (idempotent).
    - Yields the direct DSN string: "127.0.0.1:1521/XEPDB1".
    - fast-fails with pytest.fail() if Oracle or toxiproxy cannot be reached,
      so CI never hangs past the configured timeout.

  oracle_xe_fault (function-scoped, depends on oracle_xe)
    - Yields a ToxiproxyProxy object for per-test toxic management.
    - Clears ALL toxics at fixture ENTRY (guard against previous-test crash).
    - Clears ALL toxics at fixture EXIT unconditionally (no toxic leaks).

Both fixtures require Oracle XE and toxiproxy to be running. Start them with:
    docker compose -f docker-compose.test.yml up -d

In CI the GHA oracle-fault-injection job declares the service containers.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Generator, List

import oracledb
import pytest

from ._infra_topology import (
    ORACLE_PROXY_NAME,
    ORACLE_PROXY_UPSTREAM,
    ORACLE_READINESS_TIMEOUT_S,
    ORACLE_TEST_PASSWORD,
    ORACLE_TEST_USER,
    TOXIPROXY_ORACLE_LISTEN_PORT,
    oracle_direct_dsn,
    oracle_proxied_dsn,
    toxiproxy_admin_url,
)


# ---------------------------------------------------------------------------
# ToxiproxyProxy — thin HTTP client for a single toxiproxy proxy entry
# ---------------------------------------------------------------------------


@dataclass
class ToxiproxyProxy:
    """Programmatic interface for adding/removing toxics on one toxiproxy proxy.

    All toxics registered via add_toxic() are tracked in _registered_toxics.
    The oracle_xe_fault fixture calls clear_toxics() both at entry and exit,
    so no toxic survives across test function boundaries.
    """

    proxied_dsn: str
    _admin_url: str
    _proxy_name: str
    _registered_toxics: List[str] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_toxic(self, name: str, kind: str, attrs: dict) -> None:
        """Register a toxic on this proxy.

        Parameters
        ----------
        name:  Unique toxic name (used to delete it later).
        kind:  Toxiproxy type string, e.g. "latency", "timeout", "bandwidth",
               "slow_close", "reset_peer", "slicer".
        attrs: Type-specific attribute dict, e.g. {"latency": 500, "jitter": 0}.
        """
        payload = json.dumps({
            "name": name,
            "type": kind,
            "stream": "downstream",
            "toxicity": 1.0,
            "attributes": attrs,
        }).encode()
        req = urllib.request.Request(
            f"{self._admin_url}/proxies/{self._proxy_name}/toxics",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
        self._registered_toxics.append(name)

    def remove_toxic(self, name: str) -> None:
        """Delete a single toxic by name; silently ignores 404."""
        req = urllib.request.Request(
            f"{self._admin_url}/proxies/{self._proxy_name}/toxics/{name}",
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=5):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        if name in self._registered_toxics:
            self._registered_toxics.remove(name)

    def list_toxics(self) -> list:
        """Return a list of all toxic dicts currently registered on this proxy."""
        req = urllib.request.Request(
            f"{self._admin_url}/proxies/{self._proxy_name}/toxics",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())

    def clear_toxics(self) -> None:
        """Delete every toxic currently on this proxy.

        Silently tolerates unreachable toxiproxy (prevents teardown errors
        from masking actual test failures).
        """
        try:
            toxics = self.list_toxics()
        except Exception:
            return
        for toxic in toxics:
            try:
                self.remove_toxic(toxic["name"])
            except Exception:
                pass
        self._registered_toxics.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wait_for_oracle(dsn: str, user: str, password: str, timeout_s: int) -> None:
    """Poll Oracle until it accepts connections or the timeout elapses.

    Calls pytest.fail() on timeout so the test suite gets a clear error and
    CI does not hang indefinitely.
    """
    deadline = time.monotonic() + timeout_s
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            conn = oracledb.connect(user=user, password=password, dsn=dsn)
            conn.close()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(3)

    pytest.fail(
        f"Oracle XE not ready after {timeout_s}s at {dsn!r}. "
        f"Last error: {last_exc}\n"
        "Check container logs:\n"
        "  docker compose -f docker-compose.test.yml logs oracle-xe\n"
        "Or in CI: inspect the 'oracle-xe' service container log in the Actions run."
    )


def _wait_for_toxiproxy(admin_url: str, timeout_s: int = 30) -> None:
    """Poll toxiproxy admin API until it responds or the timeout elapses."""
    deadline = time.monotonic() + timeout_s
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{admin_url}/proxies", timeout=3) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_exc = exc
            time.sleep(1)

    pytest.fail(
        f"Toxiproxy admin API not ready after {timeout_s}s at {admin_url!r}. "
        f"Last error: {last_exc}\n"
        "Check container logs:\n"
        "  docker compose -f docker-compose.test.yml logs toxiproxy"
    )


def _ensure_toxiproxy_proxy(
    admin_url: str,
    proxy_name: str,
    listen_port: int,
    upstream: str,
) -> None:
    """Create an Oracle proxy entry in toxiproxy if it does not already exist."""
    # Check for existing proxy
    try:
        with urllib.request.urlopen(
            f"{admin_url}/proxies/{proxy_name}", timeout=5
        ) as resp:
            if resp.status == 200:
                return  # already exists
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    except Exception:
        pass  # will surface on the create attempt below

    payload = json.dumps({
        "name": proxy_name,
        "listen": f"0.0.0.0:{listen_port}",
        "upstream": upstream,
        "enabled": True,
    }).encode()
    req = urllib.request.Request(
        f"{admin_url}/proxies",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def oracle_xe() -> Generator[str, None, None]:
    """Session-scoped: Oracle XE ready + toxiproxy proxy created.

    Polls Oracle for up to ORACLE_READINESS_TIMEOUT_S seconds.
    Calls pytest.fail() if Oracle or toxiproxy cannot be reached, so the
    test run fails fast rather than hanging.

    Yields the direct DSN string: "127.0.0.1:1521/XEPDB1".
    """
    admin_url = toxiproxy_admin_url()
    direct_dsn = oracle_direct_dsn()

    _wait_for_oracle(
        dsn=direct_dsn,
        user=ORACLE_TEST_USER,
        password=ORACLE_TEST_PASSWORD,
        timeout_s=ORACLE_READINESS_TIMEOUT_S,
    )
    _wait_for_toxiproxy(admin_url=admin_url)
    _ensure_toxiproxy_proxy(
        admin_url=admin_url,
        proxy_name=ORACLE_PROXY_NAME,
        listen_port=TOXIPROXY_ORACLE_LISTEN_PORT,
        upstream=ORACLE_PROXY_UPSTREAM,
    )

    yield direct_dsn
    # Session teardown: containers are owned by docker-compose / GHA services.


@pytest.fixture()
def oracle_xe_fault(oracle_xe: str) -> Generator[ToxiproxyProxy, None, None]:
    """Function-scoped: clean ToxiproxyProxy for per-test fault injection.

    Clears all toxics at ENTRY (guard against previous-test crash leaving
    toxics behind) and at EXIT unconditionally, so no toxic survives across
    test function boundaries.

    Yields a ToxiproxyProxy whose .proxied_dsn routes through toxiproxy.
    """
    proxy = ToxiproxyProxy(
        proxied_dsn=oracle_proxied_dsn(),
        _admin_url=toxiproxy_admin_url(),
        _proxy_name=ORACLE_PROXY_NAME,
    )
    proxy.clear_toxics()  # entry guard

    yield proxy

    proxy.clear_toxics()  # unconditional exit cleanup
