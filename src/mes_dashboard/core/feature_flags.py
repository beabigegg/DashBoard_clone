# -*- coding: utf-8 -*-
"""Shared helpers for boolean parsing and feature-flag resolution."""

from __future__ import annotations

import os
from typing import Any, Mapping


_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def parse_bool(value: Any, default: bool = False) -> bool:
    """Parse bool-like values with explicit true/false token support."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    if not text:
        return default
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return default


def resolve_bool_flag(
    env_key: str,
    *,
    config: Mapping[str, Any] | None = None,
    config_key: str | None = None,
    default: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Resolve bool flag using precedence: environment > config > default."""
    env = environ or os.environ
    env_value = env.get(env_key)
    if env_value is not None:
        return parse_bool(env_value, default=default)

    cfg = config or {}
    key = config_key or env_key
    if key in cfg:
        return parse_bool(cfg.get(key), default=default)
    return default
