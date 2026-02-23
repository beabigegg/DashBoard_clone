# -*- coding: utf-8 -*-
"""Lightweight in-process rate limiting helpers for high-cost routes."""

from __future__ import annotations

import os
import threading
import time
from ipaddress import ip_address, ip_network
from collections import defaultdict, deque
from functools import wraps
from typing import Callable, Deque

from flask import request

from mes_dashboard.core.response import TOO_MANY_REQUESTS, error_response

_RATE_LOCK = threading.Lock()
_RATE_ATTEMPTS: dict[str, dict[str, Deque[float]]] = defaultdict(lambda: defaultdict(deque))


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(default)
    return max(value, 1)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _trusted_proxy_networks() -> list:
    raw = os.getenv("TRUSTED_PROXY_IPS", "")
    if not raw:
        return []

    networks = []
    for token in raw.split(","):
        candidate = token.strip()
        if not candidate:
            continue
        try:
            if "/" in candidate:
                networks.append(ip_network(candidate, strict=False))
            else:
                if ":" in candidate:
                    networks.append(ip_network(f"{candidate}/128", strict=False))
                else:
                    networks.append(ip_network(f"{candidate}/32", strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted_proxy_source(remote_addr: str | None) -> bool:
    if not _env_bool("TRUST_PROXY_HEADERS", False):
        return False
    if not remote_addr:
        return False

    networks = _trusted_proxy_networks()
    if not networks:
        # Explicit proxy trust mode requires explicit trusted source list.
        return False

    try:
        remote_ip = ip_address(remote_addr.strip())
    except ValueError:
        return False

    return any(remote_ip in network for network in networks)


def _client_identifier() -> str:
    remote = request.remote_addr
    if _is_trusted_proxy_source(remote):
        forwarded = request.headers.get("X-Forwarded-For", "").strip()
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            try:
                return str(ip_address(candidate))
            except ValueError:
                pass
    return remote or "unknown"


def check_and_record(
    bucket: str,
    *,
    client_id: str,
    max_attempts: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """Check and record request attempt for a bucket+client pair."""
    now = time.time()
    window_start = now - max(window_seconds, 1)

    with _RATE_LOCK:
        per_bucket = _RATE_ATTEMPTS[bucket]
        attempts = per_bucket[client_id]

        while attempts and attempts[0] <= window_start:
            attempts.popleft()

        if len(attempts) >= max_attempts:
            retry_after = max(int(window_seconds - (now - attempts[0])), 1)
            return True, retry_after

        attempts.append(now)
        return False, 0


def configured_rate_limit(
    *,
    bucket: str,
    max_attempts_env: str,
    window_seconds_env: str,
    default_max_attempts: int,
    default_window_seconds: int,
) -> Callable:
    """Build a route decorator with env-configurable rate limits."""
    max_attempts = _env_int(max_attempts_env, default_max_attempts)
    window_seconds = _env_int(window_seconds_env, default_window_seconds)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapped(*args, **kwargs):
            limited, retry_after = check_and_record(
                bucket,
                client_id=_client_identifier(),
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
            if limited:
                return error_response(
                    TOO_MANY_REQUESTS,
                    "請求過於頻繁，請稍後再試",
                    status_code=429,
                    meta={"retry_after_seconds": retry_after},
                    headers={"Retry-After": str(retry_after)},
                )
            return func(*args, **kwargs)

        return wrapped

    return decorator


def reset_rate_limits_for_tests() -> None:
    with _RATE_LOCK:
        _RATE_ATTEMPTS.clear()
