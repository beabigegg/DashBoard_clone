# -*- coding: utf-8 -*-
"""Unit tests for global_concurrency module (Task 8.3).

Covers:
- acquire_heavy_query_slot(): below limit, at limit, Redis unavailable (fail-open)
- release_heavy_query_slot(): removes from sorted set, handles Redis error
- get_active_slot_count(): correct count, returns 0 on Redis unavailable
- Expired entry cleanup is part of the Lua script path exercised via acquire
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


import mes_dashboard.core.global_concurrency as gc_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_acquire_script():
    """Force re-registration of the Lua acquire script between tests."""
    gc_mod._acquire_script = None


# ---------------------------------------------------------------------------
# acquire_heavy_query_slot
# ---------------------------------------------------------------------------

class TestAcquireHeavyQuerySlot:
    def setup_method(self):
        _reset_acquire_script()

    def test_returns_true_and_adds_to_sorted_set_when_below_limit(self):
        """Should return True and call the Lua script when under the concurrency limit."""
        mock_conn = MagicMock()
        mock_script = MagicMock(return_value=1)
        mock_conn.register_script.return_value = mock_script

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            result = gc_mod.acquire_heavy_query_slot("owner-1")

        assert result is True
        mock_script.assert_called_once()
        call_args = mock_script.call_args
        assert call_args.kwargs["args"][3] == "owner-1"

    def test_returns_false_when_at_concurrency_limit(self):
        """Should return False when the Lua script reports the limit is reached (returns 0)."""
        mock_conn = MagicMock()
        mock_script = MagicMock(return_value=0)
        mock_conn.register_script.return_value = mock_script

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            result = gc_mod.acquire_heavy_query_slot("owner-limit")

        assert result is False

    def test_returns_true_fail_open_when_redis_unavailable(self):
        """Should return True (fail-open) when get_redis_client() returns None."""
        with patch.object(gc_mod, "get_redis_client", return_value=None):
            result = gc_mod.acquire_heavy_query_slot("owner-no-redis")

        assert result is True

    def test_returns_true_fail_open_when_lua_script_raises(self):
        """Should return True (fail-open) when the Lua script execution raises."""
        mock_conn = MagicMock()
        mock_script = MagicMock(side_effect=RuntimeError("NOSCRIPT"))
        mock_conn.register_script.return_value = mock_script

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            result = gc_mod.acquire_heavy_query_slot("owner-exc")

        assert result is True

    def test_lua_script_receives_correct_argv_structure(self):
        """Lua ARGV should contain [now, cutoff, max_concurrent, owner_id, ttl]."""
        mock_conn = MagicMock()
        mock_script = MagicMock(return_value=1)
        mock_conn.register_script.return_value = mock_script

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn), \
             patch.object(gc_mod, "HEAVY_QUERY_MAX_CONCURRENT", 5):
            gc_mod.acquire_heavy_query_slot("owner-argv", ttl=300)

        call_args = mock_script.call_args
        args = call_args.kwargs["args"]
        # args: [str(now), str(cutoff), str(max_concurrent), owner_id, str(ttl)]
        assert len(args) == 5
        assert args[2] == "5"
        assert args[3] == "owner-argv"
        assert args[4] == "300"

    def test_script_registered_only_once_across_calls(self):
        """The Lua script should be registered exactly once (cached in _acquire_script)."""
        mock_conn = MagicMock()
        mock_script = MagicMock(return_value=1)
        mock_conn.register_script.return_value = mock_script

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            gc_mod.acquire_heavy_query_slot("owner-a")
            gc_mod.acquire_heavy_query_slot("owner-b")

        mock_conn.register_script.assert_called_once()


# ---------------------------------------------------------------------------
# release_heavy_query_slot
# ---------------------------------------------------------------------------

class TestReleaseHeavyQuerySlot:
    def test_calls_zrem_with_correct_owner(self):
        """Should call conn.zrem() to remove the owner from the sorted set."""
        mock_conn = MagicMock()
        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn), \
             patch.object(gc_mod, "_slot_key", return_value="mes_wip:heavy_query_slots"):
            gc_mod.release_heavy_query_slot("owner-to-release")

        mock_conn.zrem.assert_called_once_with("mes_wip:heavy_query_slots", "owner-to-release")

    def test_silently_returns_when_redis_unavailable(self):
        """Should not raise when get_redis_client() returns None."""
        with patch.object(gc_mod, "get_redis_client", return_value=None):
            gc_mod.release_heavy_query_slot("owner-no-redis")
        # No exception = pass

    def test_silently_handles_zrem_error(self):
        """Should not raise when conn.zrem() raises an exception."""
        mock_conn = MagicMock()
        mock_conn.zrem.side_effect = ConnectionError("pipe reset")
        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            gc_mod.release_heavy_query_slot("owner-err")
        # No exception = pass


# ---------------------------------------------------------------------------
# get_active_slot_count
# ---------------------------------------------------------------------------

class TestGetActiveSlotCount:
    def test_returns_correct_count_after_cleanup(self):
        """Should return the integer result of zcard after removing expired entries."""
        mock_conn = MagicMock()
        mock_conn.zcard.return_value = 2

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            count = gc_mod.get_active_slot_count()

        assert count == 2
        mock_conn.zremrangebyscore.assert_called_once()
        mock_conn.zcard.assert_called_once()

    def test_returns_zero_when_redis_unavailable(self):
        """Should return 0 when get_redis_client() returns None."""
        with patch.object(gc_mod, "get_redis_client", return_value=None):
            count = gc_mod.get_active_slot_count()
        assert count == 0

    def test_returns_zero_on_redis_exception(self):
        """Should return 0 when zremrangebyscore or zcard raises."""
        mock_conn = MagicMock()
        mock_conn.zremrangebyscore.side_effect = ConnectionError("timeout")
        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            count = gc_mod.get_active_slot_count()
        assert count == 0

    def test_returns_zero_when_no_active_slots(self):
        """Should return 0 when the sorted set is empty."""
        mock_conn = MagicMock()
        mock_conn.zcard.return_value = 0
        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            count = gc_mod.get_active_slot_count()
        assert count == 0


# ---------------------------------------------------------------------------
# Lua script expiry cleanup (behavioral contract test)
# ---------------------------------------------------------------------------

class TestLuaScriptExpiredEntriesCleanup:
    """Verify the Lua script ARGV passes a valid expiry cutoff.

    The Lua _LUA_ACQUIRE script uses ARGV[2] (cutoff = now - ttl) to call
    ZREMRANGEBYSCORE.  We verify the Python layer supplies a cutoff that is
    strictly less than now so expired members are removed before counting.
    """

    def setup_method(self):
        _reset_acquire_script()

    def test_cutoff_is_less_than_current_time(self):
        """ARGV[2] (cutoff) should be strictly less than ARGV[1] (now)."""
        captured_args = {}
        mock_conn = MagicMock()

        def _capture_script(lua_src):
            def _run_script(keys, args):
                captured_args["now"] = float(args[0])
                captured_args["cutoff"] = float(args[1])
                return 1
            return _run_script

        mock_conn.register_script.side_effect = _capture_script

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn):
            gc_mod.acquire_heavy_query_slot("owner-cutoff", ttl=600)

        assert "now" in captured_args
        assert "cutoff" in captured_args
        assert captured_args["cutoff"] < captured_args["now"]
        # Specifically the difference should equal the TTL
        assert abs((captured_args["now"] - captured_args["cutoff"]) - 600) < 2.0

    def test_max_concurrent_passed_to_script(self):
        """ARGV[3] should reflect the HEAVY_QUERY_MAX_CONCURRENT configuration."""
        captured_args = {}
        mock_conn = MagicMock()

        def _capture_script(lua_src):
            def _run_script(keys, args):
                captured_args["max_concurrent"] = int(args[2])
                return 1
            return _run_script

        mock_conn.register_script.side_effect = _capture_script

        with patch.object(gc_mod, "get_redis_client", return_value=mock_conn), \
             patch.object(gc_mod, "HEAVY_QUERY_MAX_CONCURRENT", 7):
            gc_mod.acquire_heavy_query_slot("owner-max")

        assert captured_args["max_concurrent"] == 7
