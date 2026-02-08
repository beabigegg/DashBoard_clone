# -*- coding: utf-8 -*-
"""Authentication service using LDAP API or local credentials."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Timeout for LDAP API requests
LDAP_TIMEOUT = 10

# Configuration - MUST be set in .env file
ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "").lower().split(",")

# Local authentication configuration (for development/testing)
def _resolve_local_auth_enabled(
    raw_value: str | None = None,
    flask_env: str | None = None,
) -> bool:
    """Resolve local auth toggle with production safety guard."""
    requested = (raw_value if raw_value is not None else os.environ.get("LOCAL_AUTH_ENABLED", "false"))
    local_auth_requested = str(requested).strip().lower() in ("true", "1", "yes", "on")

    effective_env = (flask_env if flask_env is not None else os.environ.get("FLASK_ENV", "development"))
    normalized_env = str(effective_env).strip().lower()
    is_production = normalized_env in {"production", "prod"}

    if local_auth_requested and is_production:
        logger.error("LOCAL_AUTH_ENABLED is blocked in production environment")
        return False

    return local_auth_requested


LOCAL_AUTH_ENABLED = _resolve_local_auth_enabled()
LOCAL_AUTH_USERNAME = os.environ.get("LOCAL_AUTH_USERNAME", "")
LOCAL_AUTH_PASSWORD = os.environ.get("LOCAL_AUTH_PASSWORD", "")

# LDAP endpoint hardening configuration
LDAP_API_URL = os.environ.get("LDAP_API_URL", "").strip()
LDAP_ALLOWED_HOSTS_RAW = os.environ.get("LDAP_ALLOWED_HOSTS", "").strip()


def _normalize_host(host: str) -> str:
    return host.strip().lower().rstrip(".")


def _parse_allowed_hosts(raw_hosts: str) -> tuple[str, ...]:
    if not raw_hosts:
        return tuple()

    hosts: list[str] = []
    for raw in raw_hosts.split(","):
        host = _normalize_host(raw)
        if host:
            hosts.append(host)
    return tuple(hosts)


def _validate_ldap_api_url(raw_url: str, allowed_hosts: tuple[str, ...]) -> tuple[str | None, str | None]:
    """Validate LDAP API URL to prevent configuration-based SSRF risks."""
    url = (raw_url or "").strip()
    if not url:
        return None, "LDAP_API_URL is missing"

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = _normalize_host(parsed.hostname or "")

    if not host:
        return None, f"LDAP_API_URL has no valid host: {url!r}"

    if scheme != "https":
        return None, f"LDAP_API_URL must use HTTPS: {url!r}"

    effective_allowlist = allowed_hosts or (host,)
    if host not in effective_allowlist:
        return None, (
            f"LDAP_API_URL host {host!r} is not allowlisted. "
            f"Allowed hosts: {', '.join(effective_allowlist)}"
        )

    return url.rstrip("/"), None


def _resolve_ldap_config() -> tuple[str | None, str | None, tuple[str, ...]]:
    allowed_hosts = _parse_allowed_hosts(LDAP_ALLOWED_HOSTS_RAW)
    api_base, error = _validate_ldap_api_url(LDAP_API_URL, allowed_hosts)

    if api_base:
        effective_hosts = allowed_hosts or (_normalize_host(urlparse(api_base).hostname or ""),)
        return api_base, None, effective_hosts

    return None, error, allowed_hosts


LDAP_API_BASE, LDAP_CONFIG_ERROR, LDAP_ALLOWED_HOSTS = _resolve_ldap_config()


def _authenticate_local(username: str, password: str) -> dict | None:
    """Authenticate using local environment credentials.

    Args:
        username: User provided username
        password: User provided password

    Returns:
        User info dict on success, None on failure
    """
    if not LOCAL_AUTH_ENABLED:
        return None

    if not LOCAL_AUTH_USERNAME or not LOCAL_AUTH_PASSWORD:
        logger.warning("Local auth enabled but credentials not configured")
        return None

    if username == LOCAL_AUTH_USERNAME and password == LOCAL_AUTH_PASSWORD:
        logger.info("Local auth success for user: %s", username)
        return {
            "username": username,
            "displayName": f"Local User ({username})",
            "mail": f"{username}@local.dev",
            "department": "Development",
        }

    logger.warning("Local auth failed for user: %s", username)
    return None


def authenticate(username: str, password: str, domain: str = "PANJIT") -> dict | None:
    """Authenticate user via local credentials or LDAP API.

    If LOCAL_AUTH_ENABLED is set, tries local authentication first.
    Falls back to LDAP API if local auth is disabled or fails.

    Args:
        username: Employee ID or email
        password: User password
        domain: Domain name (default: PANJIT)

    Returns:
        User info dict on success: {username, displayName, mail, department}
        None on failure
    """
    # Try local authentication first if enabled
    if LOCAL_AUTH_ENABLED:
        local_result = _authenticate_local(username, password)
        if local_result:
            return local_result
        # If local auth is enabled but failed, don't fall back to LDAP
        # This ensures local-only mode when LOCAL_AUTH_ENABLED is true
        return None

    if LDAP_CONFIG_ERROR:
        logger.error("LDAP authentication blocked: %s", LDAP_CONFIG_ERROR)
        return None

    if not LDAP_API_BASE:
        logger.error("LDAP authentication blocked: LDAP_API_URL is not configured")
        return None

    # LDAP authentication
    try:
        response = requests.post(
            f"{LDAP_API_BASE}/api/v1/ldap/auth",
            json={"username": username, "password": password, "domain": domain},
            timeout=LDAP_TIMEOUT,
        )
        data = response.json()

        if data.get("success"):
            user = data.get("user", {})
            logger.info("LDAP auth success for user: %s", user.get("username"))
            return user

        logger.warning("LDAP auth failed for user: %s", username)
        return None

    except requests.Timeout:
        logger.error("LDAP API timeout for user: %s", username)
        return None
    except requests.RequestException as e:
        logger.error("LDAP API error for user %s: %s", username, e)
        return None
    except (ValueError, KeyError) as e:
        logger.error("LDAP API response parse error: %s", e)
        return None


def is_admin(user: dict) -> bool:
    """Check if user is an admin.

    Args:
        user: User info dict with 'mail' field

    Returns:
        True if user email is in ADMIN_EMAILS list, or if local auth is enabled
    """
    # Local auth users are automatically admins (for development/testing)
    if LOCAL_AUTH_ENABLED:
        user_mail = user.get("mail", "")
        if user_mail.endswith("@local.dev"):
            return True

    user_mail = user.get("mail", "").lower().strip()
    allowed_emails = [e.strip() for e in ADMIN_EMAILS if e and e.strip()]
    return user_mail in allowed_emails
