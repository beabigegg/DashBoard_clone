# -*- coding: utf-8 -*-
"""Single source of truth for test infrastructure topology.

All service names, port numbers, image tags, credentials, and env-var keys
used by Oracle XE + toxiproxy fixtures are defined here.

Both ``docker-compose.test.yml`` and ``.github/workflows/backend-tests.yml``
MUST reflect the same values. If you change anything here, update both YAML
files in the same commit — there is no automated sync.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Oracle XE 21c  (gvenzl/oracle-xe:21-slim)
# ---------------------------------------------------------------------------

ORACLE_XE_IMAGE: str = "gvenzl/oracle-xe:21-slim"

# Service / container name used in docker-compose and GHA services block
ORACLE_XE_SERVICE: str = "oracle-xe"

# Port Oracle listens on inside the container (and the host-mapped port)
ORACLE_XE_PORT: int = 1521

# Pluggable database name created by gvenzl/oracle-xe images
ORACLE_XE_PDB: str = "XEPDB1"

# SYS-equivalent password (maps to ORACLE_PASSWORD env var in the container)
ORACLE_SYS_PASSWORD: str = "MES_SYS_PW_1"

# Application test user / password (APP_USER + APP_USER_PASSWORD env vars)
ORACLE_TEST_USER: str = "mes_test"
ORACLE_TEST_PASSWORD: str = "mes_test_pw"

# Maximum seconds the oracle_xe fixture waits for the DB to accept connections
ORACLE_READINESS_TIMEOUT_S: int = 240

# ---------------------------------------------------------------------------
# Toxiproxy  (shopify/toxiproxy:2.9)
# ---------------------------------------------------------------------------

TOXIPROXY_IMAGE: str = "shopify/toxiproxy:2.9"

# Service / container name
TOXIPROXY_SERVICE: str = "toxiproxy"

# Toxiproxy HTTP admin API port (host-mapped)
TOXIPROXY_ADMIN_PORT: int = 8474

# Port toxiproxy listens on to proxy Oracle traffic (host-mapped)
TOXIPROXY_ORACLE_LISTEN_PORT: int = 15210

# Name for the Oracle proxy entry created inside toxiproxy
ORACLE_PROXY_NAME: str = "oracle"

# Upstream address toxiproxy uses to reach Oracle from *inside* its container.
# Both docker-compose and GHA service containers place all services on the
# same Docker bridge network, so the service hostname resolves correctly.
ORACLE_PROXY_UPSTREAM: str = f"{ORACLE_XE_SERVICE}:{ORACLE_XE_PORT}"

# ---------------------------------------------------------------------------
# Convenience DSN / URL builders
# ---------------------------------------------------------------------------


def oracle_direct_dsn(host: str = "127.0.0.1", port: int = ORACLE_XE_PORT) -> str:
    """DSN for a direct (non-proxied) Oracle connection from the test host."""
    return f"{host}:{port}/{ORACLE_XE_PDB}"


def oracle_proxied_dsn(host: str = "127.0.0.1") -> str:
    """DSN for an Oracle connection routed through toxiproxy."""
    return f"{host}:{TOXIPROXY_ORACLE_LISTEN_PORT}/{ORACLE_XE_PDB}"


def toxiproxy_admin_url(host: str = "127.0.0.1") -> str:
    """Base URL for the toxiproxy HTTP admin API."""
    return f"http://{host}:{TOXIPROXY_ADMIN_PORT}"
