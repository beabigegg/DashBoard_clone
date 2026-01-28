# -*- coding: utf-8 -*-
"""Authentication service using LDAP API."""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

# Configuration
LDAP_API_BASE = os.environ.get("LDAP_API_URL", "https://adapi.panjit.com.tw")
ADMIN_EMAILS = os.environ.get(
    "ADMIN_EMAILS", "ymirliu@panjit.com.tw"
).lower().split(",")

# Timeout for LDAP API requests
LDAP_TIMEOUT = 10


def authenticate(username: str, password: str, domain: str = "PANJIT") -> dict | None:
    """Authenticate user via LDAP API.

    Args:
        username: Employee ID or email
        password: User password
        domain: Domain name (default: PANJIT)

    Returns:
        User info dict on success: {username, displayName, mail, department}
        None on failure
    """
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
        True if user email is in ADMIN_EMAILS list
    """
    user_mail = user.get("mail", "").lower().strip()
    return user_mail in [e.strip() for e in ADMIN_EMAILS]
