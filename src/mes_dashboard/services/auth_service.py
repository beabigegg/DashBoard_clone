# -*- coding: utf-8 -*-
"""Authentication service using LDAP API or local credentials."""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

# Configuration - MUST be set in .env file
LDAP_API_BASE = os.environ.get("LDAP_API_URL", "")
ADMIN_EMAILS = os.environ.get("ADMIN_EMAILS", "").lower().split(",")

# Timeout for LDAP API requests
LDAP_TIMEOUT = 10

# Local authentication configuration (for development/testing)
LOCAL_AUTH_ENABLED = os.environ.get("LOCAL_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
LOCAL_AUTH_USERNAME = os.environ.get("LOCAL_AUTH_USERNAME", "")
LOCAL_AUTH_PASSWORD = os.environ.get("LOCAL_AUTH_PASSWORD", "")


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
    return user_mail in [e.strip() for e in ADMIN_EMAILS]
