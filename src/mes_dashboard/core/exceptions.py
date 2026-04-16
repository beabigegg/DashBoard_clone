# -*- coding: utf-8 -*-
"""Typed service-layer exceptions for MES Dashboard.

Exception hierarchy:

    MesServiceError
    ├── UserInputError        → HTTP 400 VALIDATION_ERROR
    ├── ResourceNotFoundError → HTTP 404 NOT_FOUND
    ├── QueryTimeoutError     → HTTP 504 QUERY_TIMEOUT
    ├── DataContractError     → HTTP 500 INTERNAL_ERROR (logged)
    └── InternalQueryError    → HTTP 500 INTERNAL_ERROR (logged)

Raise these from service functions instead of returning ``{"error": "..."}`` dicts.
The ``map_service_errors`` route decorator in each Blueprint converts them to the
appropriate HTTP response automatically.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class MesServiceError(Exception):
    """Base class for all MES service-layer exceptions.

    Args:
        message: Human-readable error message (shown to the user).
        details: Optional structured details (e.g. ``{"column": "EQUIPMENTID"}``).
        cause: Optional underlying exception that triggered this error.
    """

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        self.cause = cause

    def __str__(self) -> str:
        return self.message


class UserInputError(MesServiceError):
    """Raised when the caller supplied invalid or missing input parameters.

    Maps to HTTP 400 with error code ``VALIDATION_ERROR``.
    """


class ResourceNotFoundError(MesServiceError):
    """Raised when a requested resource (LOT, equipment, …) does not exist.

    Maps to HTTP 404 with error code ``NOT_FOUND``.
    """


class QueryTimeoutError(MesServiceError):
    """Raised when an Oracle query exceeds its configured timeout.

    Maps to HTTP 504 with error code ``QUERY_TIMEOUT``.
    Typical causes: ``ORA-01013`` (user requested cancel / timeout),
    ``ORA-12170`` (connect timeout), ``ORA-04068`` (DDL lock timeout).
    """


class DataContractError(MesServiceError):
    """Raised when the DB returns rows that violate the expected schema.

    Maps to HTTP 500 with error code ``INTERNAL_ERROR``.
    Always logged at ``ERROR`` level so ops can detect schema drift.
    """


class InternalQueryError(MesServiceError):
    """Raised for unexpected errors during a DB query (connection drops, OOM, …).

    Maps to HTTP 500 with error code ``INTERNAL_ERROR``.
    The ``cause`` attribute holds the original exception and its traceback
    is logged at ``ERROR`` level.
    """


class LockUnavailableError(MesServiceError):
    """Raised when a distributed lock cannot be acquired and fail_mode="raise".

    Callers that require exclusivity (e.g. leader election, spool cleanup) should
    catch this, log at WARN, and skip the current tick.

    ``details`` typically contains ``{"lock_name": "<name>"}`` so callers can
    include the lock name in their log messages without re-parsing the message.
    ``cause`` holds the original Redis exception when acquisition failed due to
    a connection error (may be ``None`` when the Redis client was ``None``).
    """
