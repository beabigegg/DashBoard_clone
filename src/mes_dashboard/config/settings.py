"""Application configuration classes for MES Dashboard."""

from __future__ import annotations

import os
from typing import Type


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    value = os.getenv(name, default)
    if not value:
        return tuple()
    return tuple(item.strip() for item in value.split(",") if item.strip())


class Config:
    """Base configuration."""

    DEBUG = False
    TESTING = False
    ENV = "production"

    # Whether the `/internal/metrics` blueprint is imported + registered.
    # Defaults to False so production never even imports the module.  Only
    # TestingConfig flips this on, which the nightly / soak workflows reuse
    # by calling create_app("testing").  This is Layer 1 of the three-layer
    # gate defined in openspec harden-real-infra-test-coverage / 3.1.
    # Flask's ``Config.from_object()`` only copies UPPERCASE attributes, so
    # the key name is intentionally capitalised.
    REGISTER_INTERNAL_METRICS = False

    # Database pool defaults (can be overridden by env)
    DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 5)
    DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 10)
    DB_POOL_TIMEOUT = _int_env("DB_POOL_TIMEOUT", 30)
    DB_POOL_RECYCLE = _int_env("DB_POOL_RECYCLE", 1800)
    DB_TCP_CONNECT_TIMEOUT = _int_env("DB_TCP_CONNECT_TIMEOUT", 10)
    DB_CONNECT_RETRY_COUNT = _int_env("DB_CONNECT_RETRY_COUNT", 1)
    DB_CONNECT_RETRY_DELAY = _float_env("DB_CONNECT_RETRY_DELAY", 1.0)
    DB_CALL_TIMEOUT_MS = _int_env("DB_CALL_TIMEOUT_MS", 55000)

    # Slow-query settings (isolated from main request pool)
    DB_SLOW_CALL_TIMEOUT_MS = _int_env("DB_SLOW_CALL_TIMEOUT_MS", 300000)  # 300s
    DB_SLOW_MAX_CONCURRENT = _int_env("DB_SLOW_MAX_CONCURRENT", 5)
    DB_SLOW_POOL_ENABLED = _bool_env("DB_SLOW_POOL_ENABLED", True)
    DB_SLOW_POOL_SIZE = _int_env("DB_SLOW_POOL_SIZE", 2)
    DB_SLOW_POOL_MAX_OVERFLOW = _int_env("DB_SLOW_POOL_MAX_OVERFLOW", 1)
    DB_SLOW_POOL_TIMEOUT = _int_env("DB_SLOW_POOL_TIMEOUT", 30)
    DB_SLOW_POOL_RECYCLE = _int_env("DB_SLOW_POOL_RECYCLE", 1800)

    # Auth configuration - MUST be set in .env file
    LDAP_API_URL = os.getenv("LDAP_API_URL", "")
    ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "")
    SECRET_KEY = os.getenv("SECRET_KEY")
    CSRF_ENABLED = _bool_env("CSRF_ENABLED", True)
    PORTAL_SPA_ENABLED = _bool_env("PORTAL_SPA_ENABLED", True)

    # Hardening configuration (safe-by-default)
    MAX_JSON_BODY_BYTES = _int_env("MAX_JSON_BODY_BYTES", 262144)  # 256 KB
    QUERY_TOOL_MAX_CONTAINER_IDS = _int_env("QUERY_TOOL_MAX_CONTAINER_IDS", 200)
    RESOURCE_DETAIL_DEFAULT_LIMIT = _int_env("RESOURCE_DETAIL_DEFAULT_LIMIT", 500)
    RESOURCE_DETAIL_MAX_LIMIT = _int_env("RESOURCE_DETAIL_MAX_LIMIT", 500)
    TRUST_PROXY_HEADERS = _bool_env("TRUST_PROXY_HEADERS", False)
    TRUSTED_PROXY_IPS = _csv_env("TRUSTED_PROXY_IPS")
    CSP_ALLOW_UNSAFE_EVAL = _bool_env("CSP_ALLOW_UNSAFE_EVAL", False)

    # Session configuration
    PERMANENT_SESSION_LIFETIME = _int_env("SESSION_LIFETIME", 28800)  # 8 hours

    # Realtime Equipment Status Cache
    REALTIME_EQUIPMENT_CACHE_ENABLED = os.getenv(
        "REALTIME_EQUIPMENT_CACHE_ENABLED", "true"
    ).lower() in ("true", "1", "yes")
    EQUIPMENT_STATUS_SYNC_INTERVAL = _int_env("EQUIPMENT_STATUS_SYNC_INTERVAL", 300)  # 5 minutes

    # Workcenter Mapping Cache
    WORKCENTER_MAPPING_SYNC_INTERVAL = _int_env("WORKCENTER_MAPPING_SYNC_INTERVAL", 86400)  # 24 hours

    # AI-Assisted Reporting — Phase 2
    AI_QUERY_ENABLED = _bool_env("AI_QUERY_ENABLED", False)
    AI_API_URL = os.getenv("AI_API_URL", "https://ollama_pjapi.theaken.com")
    AI_API_KEY = os.getenv("AI_API_KEY")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-oss:120b")
    AI_REQUEST_TIMEOUT = _int_env("AI_REQUEST_TIMEOUT", 30)
    AI_VERIFY_TLS = _bool_env("AI_VERIFY_TLS", False)
    AI_MAX_TOKENS = _int_env("AI_MAX_TOKENS", 500)
    AI_RATE_LIMIT_MAX_REQUESTS = _int_env("AI_RATE_LIMIT_MAX_REQUESTS", 3)
    AI_RATE_LIMIT_WINDOW_SECONDS = _int_env("AI_RATE_LIMIT_WINDOW_SECONDS", 60)


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    ENV = "development"

    # Smaller pool to ensure keep-alive covers all connections
    DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 2)
    DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 3)
    DB_POOL_TIMEOUT = _int_env("DB_POOL_TIMEOUT", 30)
    DB_POOL_RECYCLE = _int_env("DB_POOL_RECYCLE", 1800)
    DB_TCP_CONNECT_TIMEOUT = _int_env("DB_TCP_CONNECT_TIMEOUT", 10)
    DB_CONNECT_RETRY_COUNT = _int_env("DB_CONNECT_RETRY_COUNT", 1)
    DB_CONNECT_RETRY_DELAY = _float_env("DB_CONNECT_RETRY_DELAY", 1.0)
    DB_CALL_TIMEOUT_MS = _int_env("DB_CALL_TIMEOUT_MS", 55000)
    DB_SLOW_MAX_CONCURRENT = _int_env("DB_SLOW_MAX_CONCURRENT", 3)
    DB_SLOW_POOL_ENABLED = _bool_env("DB_SLOW_POOL_ENABLED", True)
    # pool_size + max_overflow = semaphore (2+1=3)
    DB_SLOW_POOL_SIZE = _int_env("DB_SLOW_POOL_SIZE", 2)
    DB_SLOW_POOL_MAX_OVERFLOW = _int_env("DB_SLOW_POOL_MAX_OVERFLOW", 1)


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    ENV = "production"

    DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 10)
    DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 20)
    DB_POOL_TIMEOUT = _int_env("DB_POOL_TIMEOUT", 30)
    DB_POOL_RECYCLE = _int_env("DB_POOL_RECYCLE", 1800)
    DB_TCP_CONNECT_TIMEOUT = _int_env("DB_TCP_CONNECT_TIMEOUT", 10)
    DB_CONNECT_RETRY_COUNT = _int_env("DB_CONNECT_RETRY_COUNT", 1)
    DB_CONNECT_RETRY_DELAY = _float_env("DB_CONNECT_RETRY_DELAY", 1.0)
    DB_CALL_TIMEOUT_MS = _int_env("DB_CALL_TIMEOUT_MS", 55000)
    # pool_size + max_overflow = semaphore (5+3=8)
    DB_SLOW_MAX_CONCURRENT = _int_env("DB_SLOW_MAX_CONCURRENT", 8)
    DB_SLOW_POOL_ENABLED = _bool_env("DB_SLOW_POOL_ENABLED", True)
    DB_SLOW_POOL_SIZE = _int_env("DB_SLOW_POOL_SIZE", 5)
    DB_SLOW_POOL_MAX_OVERFLOW = _int_env("DB_SLOW_POOL_MAX_OVERFLOW", 3)


class TestingConfig(Config):
    """Testing configuration."""

    DEBUG = True
    TESTING = True
    ENV = "testing"

    DB_POOL_SIZE = 1
    DB_MAX_OVERFLOW = 0
    DB_POOL_TIMEOUT = 5
    DB_POOL_RECYCLE = 300
    DB_TCP_CONNECT_TIMEOUT = 5
    DB_CONNECT_RETRY_COUNT = 0
    DB_CONNECT_RETRY_DELAY = 0.0
    DB_CALL_TIMEOUT_MS = 5000
    DB_SLOW_CALL_TIMEOUT_MS = 10000
    DB_SLOW_MAX_CONCURRENT = 1
    DB_SLOW_POOL_ENABLED = False
    CSRF_ENABLED = False

    # Testing / nightly / soak configs register the /internal/metrics
    # blueprint; the runtime env + loopback gates still apply.
    REGISTER_INTERNAL_METRICS = True


def get_config(env: str | None = None) -> Type[Config]:
    """Select config class based on environment name."""
    value = (env or os.getenv("FLASK_ENV", "production")).lower()
    if value in {"prod", "production"}:
        return ProductionConfig
    if value in {"test", "testing"}:
        return TestingConfig
    return DevelopmentConfig
