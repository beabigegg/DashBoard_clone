# -*- coding: utf-8 -*-
"""Unit tests for mes_dashboard.core.exceptions."""

import pytest

from mes_dashboard.core.exceptions import (
    MesServiceError,
    UserInputError,
    ResourceNotFoundError,
    QueryTimeoutError,
    DataContractError,
    InternalQueryError,
    LockUnavailableError,
)

_ALL_SUBCLASSES = [
    UserInputError,
    ResourceNotFoundError,
    QueryTimeoutError,
    DataContractError,
    InternalQueryError,
]


class TestSubclassInstantiation:
    """Each subclass must accept (message, details=None, cause=None)."""

    @pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
    def test_message_only(self, cls):
        exc = cls("some message")
        assert exc.message == "some message"
        assert exc.details is None
        assert exc.cause is None

    @pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
    def test_with_details(self, cls):
        exc = cls("msg", details={"column": "EQUIPMENTID"})
        assert exc.details == {"column": "EQUIPMENTID"}

    @pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
    def test_with_cause(self, cls):
        original = ValueError("root cause")
        exc = cls("msg", cause=original)
        assert exc.cause is original

    @pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
    def test_all_three_kwargs(self, cls):
        original = RuntimeError("db gone")
        exc = cls("user msg", details={"k": "v"}, cause=original)
        assert exc.message == "user msg"
        assert exc.details == {"k": "v"}
        assert exc.cause is original


class TestStrRepresentation:
    """str() should return the message field."""

    @pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
    def test_str_returns_message(self, cls):
        exc = cls("hello world")
        assert str(exc) == "hello world"


class TestInheritance:
    """Each subclass must be an instance of MesServiceError and Exception."""

    @pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
    def test_is_mes_service_error(self, cls):
        assert issubclass(cls, MesServiceError)

    @pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
    def test_is_exception(self, cls):
        assert issubclass(cls, Exception)


class TestCauseChaining:
    """cause should chain correctly when the exception is re-raised."""

    def test_cause_accessible_after_reraise(self):
        original = ConnectionError("timeout")
        exc = InternalQueryError("query failed", cause=original)

        with pytest.raises(InternalQueryError) as exc_info:
            raise exc

        assert exc_info.value.cause is original

    def test_cause_none_by_default(self):
        exc = UserInputError("bad input")
        assert exc.cause is None


class TestLockUnavailableError:
    """LockUnavailableError carries lock_name in details and chains the cause."""

    def test_with_lock_name_details_and_cause(self):
        original_exc = ConnectionError("redis gone")
        exc = LockUnavailableError(
            "lock unavailable",
            details={"lock_name": "x"},
            cause=original_exc,
        )
        assert exc.message == "lock unavailable"
        assert exc.details == {"lock_name": "x"}
        assert exc.cause is original_exc

    def test_is_mes_service_error(self):
        assert issubclass(LockUnavailableError, MesServiceError)

    def test_str_returns_message(self):
        exc = LockUnavailableError("lock unavailable")
        assert str(exc) == "lock unavailable"
