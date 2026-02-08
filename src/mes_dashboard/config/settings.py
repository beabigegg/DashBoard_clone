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


class Config:
    """Base configuration."""

    DEBUG = False
    TESTING = False
    ENV = "production"

    # Database pool defaults (can be overridden by env)
    DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 5)
    DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 10)
    DB_POOL_TIMEOUT = _int_env("DB_POOL_TIMEOUT", 30)
    DB_POOL_RECYCLE = _int_env("DB_POOL_RECYCLE", 1800)
    DB_TCP_CONNECT_TIMEOUT = _int_env("DB_TCP_CONNECT_TIMEOUT", 10)
    DB_CONNECT_RETRY_COUNT = _int_env("DB_CONNECT_RETRY_COUNT", 1)
    DB_CONNECT_RETRY_DELAY = _float_env("DB_CONNECT_RETRY_DELAY", 1.0)
    DB_CALL_TIMEOUT_MS = _int_env("DB_CALL_TIMEOUT_MS", 55000)

    # Auth configuration - MUST be set in .env file
    LDAP_API_URL = os.getenv("LDAP_API_URL", "")
    ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "")
    SECRET_KEY = os.getenv("SECRET_KEY")
    CSRF_ENABLED = _bool_env("CSRF_ENABLED", True)

    # Session configuration
    PERMANENT_SESSION_LIFETIME = _int_env("SESSION_LIFETIME", 28800)  # 8 hours

    # Realtime Equipment Status Cache
    REALTIME_EQUIPMENT_CACHE_ENABLED = os.getenv(
        "REALTIME_EQUIPMENT_CACHE_ENABLED", "true"
    ).lower() in ("true", "1", "yes")
    EQUIPMENT_STATUS_SYNC_INTERVAL = _int_env("EQUIPMENT_STATUS_SYNC_INTERVAL", 300)  # 5 minutes

    # Workcenter Mapping Cache
    WORKCENTER_MAPPING_SYNC_INTERVAL = _int_env("WORKCENTER_MAPPING_SYNC_INTERVAL", 86400)  # 24 hours


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
    CSRF_ENABLED = False


def get_config(env: str | None = None) -> Type[Config]:
    """Select config class based on environment name."""
    value = (env or os.getenv("FLASK_ENV", "development")).lower()
    if value in {"prod", "production"}:
        return ProductionConfig
    if value in {"test", "testing"}:
        return TestingConfig
    return DevelopmentConfig
