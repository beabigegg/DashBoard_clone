"""Application configuration classes for MES Dashboard."""

from __future__ import annotations

import os
from typing import Type


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    """Base configuration."""

    DEBUG = False
    TESTING = False
    ENV = "production"

    # Database pool defaults (can be overridden by env)
    DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 5)
    DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 10)


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    ENV = "development"

    DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 5)
    DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 10)


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    ENV = "production"

    DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 10)
    DB_MAX_OVERFLOW = _int_env("DB_MAX_OVERFLOW", 20)


def get_config(env: str | None = None) -> Type[Config]:
    """Select config class based on environment name."""
    value = (env or os.getenv("FLASK_ENV", "development")).lower()
    if value in {"prod", "production"}:
        return ProductionConfig
    return DevelopmentConfig
