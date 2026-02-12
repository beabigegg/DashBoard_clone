# -*- coding: utf-8 -*-
"""Tests for shared feature-flag resolution helpers."""

from __future__ import annotations

from mes_dashboard.core.feature_flags import parse_bool, resolve_bool_flag


def test_parse_bool_supports_true_and_false_tokens():
    assert parse_bool("true", default=False) is True
    assert parse_bool(" yes ", default=False) is True
    assert parse_bool("0", default=True) is False
    assert parse_bool("off", default=True) is False


def test_resolve_bool_flag_prefers_environment_over_config():
    env = {"FEATURE_X": "false"}
    config = {"FEATURE_X": True}
    assert resolve_bool_flag("FEATURE_X", config=config, default=True, environ=env) is False


def test_resolve_bool_flag_uses_config_then_default_when_env_missing():
    config = {"FEATURE_X": "true"}
    assert resolve_bool_flag("FEATURE_X", config=config, default=False, environ={}) is True
    assert resolve_bool_flag("MISSING", config=config, default=False, environ={}) is False
