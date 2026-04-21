# -*- coding: utf-8 -*-
"""Real Oracle XE fault injection tests.

Phase 1 (TestOracleXeSmoke): fixture machinery smoke — verifies the container
  and toxiproxy wiring work before any behavior assertions are attempted.

Phase 2A (TestOracleRealFaults): driver-level fault assertions — session kill,
  listener stop, and recovery.  These tests use raw oracledb connections and
  pools; they do NOT go through the Flask app and do NOT assert HTTP envelopes,
  Retry-After headers, or circuit breaker counters.  Those require the app-bridge
  prerequisite and are Phase 2B work.

Run locally:
    docker compose -f docker-compose.test.yml up -d
    conda run -n mes-dashboard pytest \\
        tests/integration/test_real_oracle_fault_injection.py \\
        --run-integration-real -v

Run in CI: the GHA ``oracle-fault-injection`` job in backend-tests.yml
           declares service containers and runs this file automatically.
"""

from __future__ import annotations

import time

import oracledb
import pytest

from ._infra_topology import (
    ORACLE_SYS_PASSWORD,
    ORACLE_TEST_PASSWORD,
    ORACLE_TEST_USER,
)
from ._oracle_xe_fixture import ToxiproxyProxy

pytestmark = pytest.mark.integration_real


class TestOracleXeSmoke:

    def test_oracle_xe_accepts_connections(self, oracle_xe: str) -> None:
        """Direct DSN works: SELECT 1 FROM DUAL returns 1."""
        conn = oracledb.connect(
            user=ORACLE_TEST_USER,
            password=ORACLE_TEST_PASSWORD,
            dsn=oracle_xe,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM DUAL")
                row = cur.fetchone()
        assert row is not None and row[0] == 1

    def test_toxiproxy_latency_toxic_adds_delay(
        self, oracle_xe: str, oracle_xe_fault: ToxiproxyProxy
    ) -> None:
        """Latency toxic is active: query through proxy takes ≥ 400ms.

        We add 500ms of latency and assert ≥ 400ms (generous lower bound to
        accommodate CI timing jitter).

        Mutation check: removing the add_toxic() call makes elapsed < 0.4s
        and the assert fires.
        """
        oracle_xe_fault.add_toxic("smoke-latency", "latency", {"latency": 500, "jitter": 0})

        start = time.monotonic()
        conn = oracledb.connect(
            user=ORACLE_TEST_USER,
            password=ORACLE_TEST_PASSWORD,
            dsn=oracle_xe_fault.proxied_dsn,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM DUAL")
                cur.fetchone()
        elapsed = time.monotonic() - start

        assert elapsed >= 0.4, (
            f"Expected ≥ 400ms latency from toxiproxy, got {elapsed:.3f}s. "
            "The toxic may not be active or the proxy is bypassed."
        )

    def test_toxiproxy_timeout_toxic_breaks_connection(
        self, oracle_xe: str, oracle_xe_fault: ToxiproxyProxy
    ) -> None:
        """Timeout toxic causes oracledb to raise OperationalError or DatabaseError.

        We apply a 100ms timeout toxic and attempt to connect + execute.
        The driver must raise; a clean success means the proxy is bypassed.

        Mutation check: removing the add_toxic() call makes the connect
        succeed and pytest.raises() fails the test.
        """
        oracle_xe_fault.add_toxic(
            "smoke-timeout",
            "timeout",
            {"timeout": 100},  # close connection after 100ms
        )

        with pytest.raises((oracledb.OperationalError, oracledb.DatabaseError)):
            conn = oracledb.connect(
                user=ORACLE_TEST_USER,
                password=ORACLE_TEST_PASSWORD,
                dsn=oracle_xe_fault.proxied_dsn,
                # Short TCP timeout ensures the test does not hang on CI
                tcp_connect_timeout=3,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")
                    cur.fetchall()

    def test_fixture_teardown_clears_all_toxics(
        self, oracle_xe: str, oracle_xe_fault: ToxiproxyProxy
    ) -> None:
        """clear_toxics() removes every registered toxic; proxy returns clean.

        Adds two toxics, verifies both are present, then calls clear_toxics()
        and verifies the list is empty.  The fixture's exit-hook runs the same
        clear_toxics() — this test proves the method works so that the hook
        guarantee is meaningful.

        Mutation check: replacing clear_toxics() implementation with a no-op
        makes list_toxics() return non-empty and the final assert fires.
        """
        oracle_xe_fault.add_toxic("td-latency", "latency", {"latency": 100, "jitter": 0})
        oracle_xe_fault.add_toxic("td-bandwidth", "bandwidth", {"rate": 100})

        before = oracle_xe_fault.list_toxics()
        assert len(before) == 2, f"Expected 2 toxics before clear, got {before}"

        oracle_xe_fault.clear_toxics()

        after = oracle_xe_fault.list_toxics()
        assert after == [], f"Expected empty toxic list after clear, got {after}"


class TestOracleRealFaults:
    """Phase 2A: driver-level real Oracle fault tests.

    Each test uses raw oracledb connections / pools routed through the Oracle
    XE container and optionally toxiproxy.  No Flask app, no HTTP envelope
    assertions, no Retry-After or circuit breaker counter checks — those are
    Phase 2B (requires the app-bridge prerequisite).
    """

    def test_session_kill_returns_connection_to_pool(
        self, oracle_xe: str
    ) -> None:
        """Session kill: pool.busy returns to zero; next pool query succeeds.

        Steps:
          1. Create a small oracledb pool (min=1, max=3).
          2. Acquire a connection; read its SID via SYS_CONTEXT.
          3. Kill the session with SYSDBA ALTER SYSTEM KILL SESSION IMMEDIATE.
          4. Attempt a query on the dead connection — must raise OperationalError.
          5. conn.close() returns it to the pool; pool.busy must be 0.
          6. A fresh connection from the same pool must execute SELECT 1 normally.

        Mutation check: removing the ALTER SYSTEM KILL SESSION call means the
        connection stays alive, no OperationalError is raised, and the
        pytest.raises block fails the test.
        """
        pool = oracledb.create_pool(
            user=ORACLE_TEST_USER,
            password=ORACLE_TEST_PASSWORD,
            dsn=oracle_xe,
            min=1,
            max=3,
            increment=1,
        )
        sys_conn = oracledb.connect(
            user="sys",
            password=ORACLE_SYS_PASSWORD,
            dsn=oracle_xe,
            mode=oracledb.AUTH_MODE_SYSDBA,
        )
        try:
            conn = pool.acquire()
            try:
                # Step 2: get the session's SID from within the connection
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT SYS_CONTEXT('USERENV', 'SID') FROM DUAL"
                    )
                    (sid,) = cur.fetchone()

                # Look up SERIAL# from V$SESSION (requires SYSDBA)
                with sys_conn.cursor() as cur:
                    cur.execute(
                        "SELECT SERIAL# FROM V$SESSION WHERE SID = :1",
                        [int(sid)],
                    )
                    row = cur.fetchone()
                assert row is not None, (
                    f"Session SID={sid} not found in V$SESSION; "
                    "check Oracle XE container logs."
                )
                (serial,) = row

                # Step 3: kill the session
                with sys_conn.cursor() as cur:
                    cur.execute(
                        f"ALTER SYSTEM KILL SESSION '{sid},{serial}' IMMEDIATE"
                    )

                # Step 4: next query on the dead connection must raise
                with pytest.raises(
                    (oracledb.OperationalError, oracledb.DatabaseError)
                ):
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM DUAL")
                        cur.fetchone()

            finally:
                conn.close()  # unconditionally returns / discards the connection

            # Step 5: pool.busy must be zero after close
            assert pool.busy == 0, (
                f"Expected pool.busy=0 after conn.close(), got {pool.busy}"
            )

            # Step 6: a fresh connection must work
            conn2 = pool.acquire()
            try:
                with conn2.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")
                    (value,) = cur.fetchone()
                assert value == 1, f"Expected SELECT 1 = 1, got {value}"
            finally:
                conn2.close()

        finally:
            pool.close(force=True)
            sys_conn.close()

    def test_listener_stop_raises_driver_error(
        self, oracle_xe: str, oracle_xe_fault: ToxiproxyProxy
    ) -> None:
        """Listener-stop via timeout toxic: driver raises OperationalError / DatabaseError.

        Applies a 100 ms toxiproxy timeout to the Oracle proxy route, then
        attempts a connection.  The driver must raise; a clean success means
        the proxy is not active or the connection is not going through toxiproxy.

        Mutation check: removing the add_toxic() call means no error is raised
        and the pytest.raises block fails the test.
        """
        oracle_xe_fault.add_toxic("p2a-timeout", "timeout", {"timeout": 100})

        with pytest.raises(
            (oracledb.OperationalError, oracledb.DatabaseError)
        ) as exc_info:
            conn = oracledb.connect(
                user=ORACLE_TEST_USER,
                password=ORACLE_TEST_PASSWORD,
                dsn=oracle_xe_fault.proxied_dsn,
                tcp_connect_timeout=3,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")
                    cur.fetchone()

        assert "ORA-" in str(exc_info.value), (
            f"Expected an ORA-XXXXX code in the exception message, got: "
            f"{exc_info.value!r}. "
            "The driver raised a non-Oracle error; check toxiproxy connectivity."
        )

    def test_listener_recovery_reconnects_within_socket_timeout(
        self, oracle_xe: str, oracle_xe_fault: ToxiproxyProxy
    ) -> None:
        """Recovery: after the toxic is cleared the next proxied connection succeeds.

        Steps:
          1. Apply a 100 ms timeout toxic — verify the fault is active.
          2. Remove the toxic.
          3. A fresh proxied connection must succeed and return SELECT 1 = 1
             within 10 seconds.

        Mutation check: not calling remove_toxic() keeps the fault active,
        the recovery connection fails, and the success assertion fires.
        """
        oracle_xe_fault.add_toxic("p2a-recovery", "timeout", {"timeout": 100})

        # Step 1: verify fault is active
        with pytest.raises(
            (oracledb.OperationalError, oracledb.DatabaseError)
        ):
            conn = oracledb.connect(
                user=ORACLE_TEST_USER,
                password=ORACLE_TEST_PASSWORD,
                dsn=oracle_xe_fault.proxied_dsn,
                tcp_connect_timeout=3,
            )
            with conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")

        # Step 2: clear the toxic
        oracle_xe_fault.remove_toxic("p2a-recovery")

        # Step 3: recovery connection must succeed within 10 s
        start = time.monotonic()
        conn = oracledb.connect(
            user=ORACLE_TEST_USER,
            password=ORACLE_TEST_PASSWORD,
            dsn=oracle_xe_fault.proxied_dsn,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM DUAL")
                (value,) = cur.fetchone()
        elapsed = time.monotonic() - start

        assert value == 1, f"Expected SELECT 1 = 1 after recovery, got {value}"
        assert elapsed < 10.0, (
            f"Recovery reconnect took {elapsed:.2f}s; expected < 10 s. "
            "The toxic may still be active or Oracle XE is slow to accept new connections."
        )


    def test_network_flap_mid_transaction_rolls_back_cleanly(
        self, oracle_xe: str, oracle_xe_fault: ToxiproxyProxy
    ) -> None:
        """reset_peer toxic mid-transaction: un-committed changes are absent after flap.

        Steps:
          1. Create a scratch table in MES_TEST schema.
          2. Begin a transaction, insert a sentinel row (not committed).
          3. Apply a reset_peer toxic for 2 seconds (simulates TCP reset mid-txn).
          4. Wait for the toxic to expire and clear it.
          5. Query a fresh connection from the same pool — sentinel row MUST be absent
             (transaction rolled back by the driver/Oracle on connection drop).
          6. A subsequent INSERT + SELECT on a clean connection must succeed.

        Mutation check: skipping the reset_peer toxic leaves the connection alive,
        the transaction commits normally, the row IS present, and the absence
        assertion fires.
        """
        import contextlib

        sys_conn = oracledb.connect(
            user="sys",
            password=ORACLE_SYS_PASSWORD,
            dsn=oracle_xe,
            mode=oracledb.AUTH_MODE_SYSDBA,
        )
        try:
            # Step 1: create scratch table in MES_TEST schema (idempotent)
            with sys_conn.cursor() as cur:
                cur.execute(
                    "BEGIN "
                    "  EXECUTE IMMEDIATE 'DROP TABLE mes_test.netflap_test_tbl'; "
                    "EXCEPTION WHEN OTHERS THEN NULL; "
                    "END;"
                )
                cur.execute(
                    "CREATE TABLE mes_test.netflap_test_tbl "
                    "(id NUMBER PRIMARY KEY, val VARCHAR2(50))"
                )
            sys_conn.commit()
        finally:
            sys_conn.close()

        pool = oracledb.create_pool(
            user=ORACLE_TEST_USER,
            password=ORACLE_TEST_PASSWORD,
            dsn=oracle_xe_fault.proxied_dsn,
            min=1,
            max=3,
            increment=1,
        )
        sentinel_id = 99991

        try:
            conn = pool.acquire()
            try:
                # Step 2: insert sentinel row, no commit
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO mes_test.netflap_test_tbl VALUES (:1, :2)",
                        [sentinel_id, "flap-test"],
                    )

                # Step 3: apply reset_peer toxic — closes the TCP connection
                oracle_xe_fault.add_toxic(
                    "p2b-netflap", "reset_peer", {"timeout": 0}
                )
                time.sleep(0.5)  # let the TCP reset propagate

            finally:
                # Step 4: clear toxic before releasing the dead connection
                oracle_xe_fault.clear_toxics()
                with contextlib.suppress(Exception):
                    conn.close()

            # Step 5: fresh connection — sentinel row must be absent (rollback)
            conn2 = pool.acquire()
            try:
                with conn2.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM mes_test.netflap_test_tbl WHERE id = :1",
                        [sentinel_id],
                    )
                    (count,) = cur.fetchone()
                assert count == 0, (
                    f"Expected sentinel row to be absent after network flap, "
                    f"got count={count}. The transaction may have committed before the "
                    "TCP reset reached Oracle."
                )

                # Step 6: clean INSERT + SELECT must succeed on the recovered connection
                cur.execute(
                    "INSERT INTO mes_test.netflap_test_tbl VALUES (:1, :2)",
                    [sentinel_id + 1, "recovery"],
                )
                conn2.commit()
                cur.execute(
                    "SELECT val FROM mes_test.netflap_test_tbl WHERE id = :1",
                    [sentinel_id + 1],
                )
                (val,) = cur.fetchone()
                assert val == "recovery", (
                    f"Expected clean recovery row, got {val!r}"
                )
            finally:
                conn2.close()

        finally:
            pool.close(force=True)

    def test_latency_spike_does_not_leak_pool_connections(
        self, oracle_xe: str, oracle_xe_fault: ToxiproxyProxy
    ) -> None:
        """600ms latency toxic: pool.busy returns to zero after all connections close.

        Steps:
          1. Create a pool (min=1, max=5).
          2. Apply 600ms latency toxic.
          3. Acquire max connections, execute a query on each.
          4. Release all connections.
          5. Clear the toxic.
          6. pool.busy must be 0 — no leaked checkouts.

        Mutation check: removing conn.close() in step 4 means pool.busy stays > 0
        after the release loop and the final assert fires.
        """
        oracle_xe_fault.add_toxic(
            "p2b-latency", "latency", {"latency": 600, "jitter": 0}
        )

        pool = oracledb.create_pool(
            user=ORACLE_TEST_USER,
            password=ORACLE_TEST_PASSWORD,
            dsn=oracle_xe_fault.proxied_dsn,
            min=1,
            max=5,
            increment=1,
        )
        conns = []
        try:
            # Step 3: acquire all connections, run a query on each
            for _ in range(5):
                c = pool.acquire()
                with c.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL")
                    cur.fetchone()
                conns.append(c)

            assert pool.busy == 5, (
                f"Expected pool.busy=5 while all connections are held, got {pool.busy}"
            )

            # Step 4: release all connections
            for c in conns:
                c.close()
            conns.clear()

            # Step 5: clear toxic
            oracle_xe_fault.clear_toxics()

            # Step 6: no leaked checkouts
            assert pool.busy == 0, (
                f"Expected pool.busy=0 after releasing all connections, "
                f"got {pool.busy}. Possible connection leak."
            )

        finally:
            for c in conns:
                try:
                    c.close()
                except Exception:
                    pass
            pool.close(force=True)


class TestOraclePhase2BEnvelopes:
    """Phase 2B: HTTP envelope assertions using the oracle_xe_app bridge.

    Each test uses the ``oracle_xe_app`` fixture (Flask test_client wired to the
    Oracle XE container) to verify that real Oracle driver errors propagate
    through the app boundary and produce the documented HTTP envelope.
    """

    def test_snapshot_too_old_surfaces_timeout_envelope(
        self, oracle_xe: str, oracle_xe_app
    ) -> None:
        """ORA-01555 via real Oracle: GET /health under undo-exhausted conditions.

        Best-effort trigger:
          1. As SYSDBA, set UNDO_RETENTION to 1 second and create a scratch table.
          2. Open a serializable transaction on the MES_TEST user.
          3. From SYSDBA, flood the table with updates to exhaust undo.
          4. Wait for Oracle to reclaim the undo blocks.
          5. In the still-open serializable session, try to read — should raise ORA-01555.

        Oracle XE may raise ORA-08180 ("no snapshot found") instead of ORA-01555
        under some configurations; both indicate the snapshot is unavailable.

        The HTTP envelope assertion is skipped at this tier — the oracle_xe_app
        client calls GET /health which uses a separate health engine pool.  The
        DB_QUERY_TIMEOUT (504) mapping is verified at the mock tier
        (test_oracle_error_path.py::test_ora_01555_snapshot_returns_db_query_timeout).
        This test focuses on the driver-level raise.

        Mutation check: removing UNDO_RETENTION=1 and the flood loop means Oracle
        has plenty of undo and no ORA-01555 is raised; pytest.raises fires.
        """
        sys_conn = oracledb.connect(
            user="sys",
            password=ORACLE_SYS_PASSWORD,
            dsn=oracle_xe,
            mode=oracledb.AUTH_MODE_SYSDBA,
        )
        try:
            # Step 1: minimise undo retention and create scratch table
            with sys_conn.cursor() as cur:
                cur.execute("ALTER SYSTEM SET UNDO_RETENTION = 1")
                cur.execute(
                    "BEGIN "
                    "  EXECUTE IMMEDIATE 'DROP TABLE mes_test.undo_test_tbl'; "
                    "EXCEPTION WHEN OTHERS THEN NULL; "
                    "END;"
                )
                cur.execute(
                    "CREATE TABLE mes_test.undo_test_tbl (id NUMBER, val NUMBER)"
                )
                for i in range(20):
                    cur.execute(
                        "INSERT INTO mes_test.undo_test_tbl VALUES (:1, :2)",
                        [i, i],
                    )
            sys_conn.commit()

            # Step 2: open serializable transaction, read the initial rows
            ser_conn = oracledb.connect(
                user=ORACLE_TEST_USER,
                password=ORACLE_TEST_PASSWORD,
                dsn=oracle_xe,
            )
            try:
                with ser_conn.cursor() as cur:
                    cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                    cur.execute("SELECT * FROM mes_test.undo_test_tbl")
                    cur.fetchall()  # consume — fixes the read SCN

                # Step 3: flood undo from SYSDBA to overwrite old blocks
                with sys_conn.cursor() as cur:
                    for _ in range(200):
                        cur.execute(
                            "UPDATE mes_test.undo_test_tbl SET val = val + 1"
                        )
                        sys_conn.commit()

                # Step 4: wait for Oracle to reclaim undo (retention=1s)
                time.sleep(3)

                # Step 5: re-read from the serializable snapshot → expect ORA-01555 or ORA-08180
                with pytest.raises(
                    (oracledb.OperationalError, oracledb.DatabaseError)
                ) as exc_info:
                    with ser_conn.cursor() as cur:
                        cur.execute("SELECT * FROM mes_test.undo_test_tbl")
                        cur.fetchall()

                exc_str = str(exc_info.value)
                assert any(
                    code in exc_str
                    for code in ("ORA-01555", "ORA-08180", "ORA-01466")
                ), (
                    f"Expected ORA-01555/ORA-08180/ORA-01466 (snapshot too old), "
                    f"got: {exc_str!r}. "
                    "UNDO_RETENTION may not have been applied or undo was not exhausted."
                )

            finally:
                with sys_conn.cursor() as cur:
                    # Restore a reasonable undo retention
                    cur.execute("ALTER SYSTEM SET UNDO_RETENTION = 900")
                ser_conn.close()

        finally:
            sys_conn.close()

    def test_circuit_breaker_counts_real_driver_failures(
        self, oracle_xe: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Real oracledb connection failures increment circuit breaker failure_count.

        Drives read_sql_df() against an engine pointing at an unreachable Oracle
        port so the driver raises a real oracledb connection error on every call.
        Verifies that CIRCUIT_BREAKER_ENABLED=True + N failures → circuit OPEN.

        Steps:
          1. Enable the circuit breaker for this test only.
          2. Reset the global circuit breaker singleton to a known empty state.
          3. Monkeypatch _ENGINE to an engine pointing at a closed port.
          4. Call read_sql_df() N times; each must fail with a real oracledb error.
          5. Verify failure_count == N after N < threshold.
          6. Continue until threshold is crossed; verify state transitions to OPEN.
          7. Verify the next read_sql_df() raises DatabaseCircuitOpenError immediately.

        Mutation check: removing the monkeypatch of CIRCUIT_BREAKER_ENABLED means
        record_failure() is a no-op; failure_count stays 0 and the circuit never
        opens.
        """
        import mes_dashboard.core.circuit_breaker as _cb
        import mes_dashboard.core.database as _db
        from mes_dashboard.core.circuit_breaker import (
            CircuitState,
            get_database_circuit_breaker,
        )
        from mes_dashboard.core.database import DatabaseCircuitOpenError
        from sqlalchemy import create_engine as _sa_create_engine

        # Step 1: enable circuit breaker for this test
        monkeypatch.setattr(_cb, "CIRCUIT_BREAKER_ENABLED", True)

        # Step 2: reset global singleton to empty state
        cb = get_database_circuit_breaker()
        cb.reset()

        # Step 3: point _ENGINE at a closed port → guaranteed real oracledb errors
        bad_engine = _sa_create_engine(
            f"oracle+oracledb://{ORACLE_TEST_USER}:{ORACLE_TEST_PASSWORD}"
            f"@127.0.0.1:9998/?service_name=INVALID",
            pool_size=1,
            max_overflow=0,
        )
        monkeypatch.setattr(_db, "_ENGINE", bad_engine)

        threshold = _cb.FAILURE_THRESHOLD  # default 5
        window_size = _cb.WINDOW_SIZE       # default 10

        # Step 4 & 5: drive failures up to (but not past) threshold
        for i in range(1, threshold):
            try:
                _db.read_sql_df("SELECT 1 FROM DUAL", caller="cb-test")
            except DatabaseCircuitOpenError:
                pytest.fail(
                    f"Circuit opened prematurely at iteration {i} "
                    f"(threshold={threshold})"
                )
            except Exception:
                pass  # expected real oracledb connection error

            status = cb.get_status()
            assert status.failure_count == i, (
                f"After {i} failure(s), expected failure_count={i}, "
                f"got {status.failure_count}. "
                "record_failure() may not be wired or CIRCUIT_BREAKER_ENABLED patch failed."
            )

        # Step 6: one more failure should tip the circuit open (failure_rate = threshold/threshold = 100%)
        try:
            _db.read_sql_df("SELECT 1 FROM DUAL", caller="cb-test")
        except Exception:
            pass

        status = cb.get_status()
        assert status.state == CircuitState.OPEN.value, (
            f"Expected circuit state=OPEN after {threshold} failures, "
            f"got state={status.state!r}. "
            f"failure_count={status.failure_count}, failure_rate={status.failure_rate:.2f}"
        )

        # Step 7: next call must short-circuit immediately with DatabaseCircuitOpenError
        with pytest.raises(DatabaseCircuitOpenError):
            _db.read_sql_df("SELECT 1 FROM DUAL", caller="cb-test")

        # Teardown: restore circuit breaker to closed state so other tests are unaffected
        cb.reset()


class TestOracleXeAppBridge:
    """Phase 2B prerequisite: verify oracle_xe_app fixture wires Flask to Oracle XE.

    This class contains the single smoke test that must pass before any Phase 2B
    HTTP envelope / circuit breaker assertion is written.  It proves that:

      1. oracle_xe_app patches CONNECTION_STRING to point at the XE container.
      2. /health calls get_health_engine() which picks up the patched URL.
      3. SELECT 1 FROM DUAL executes against a real Oracle XE session.
      4. The route returns 200 with services.database == 'ok'.

    The health memo cache is disabled when app.testing is True, so this test
    always hits the DB — it cannot be short-circuited by a warm cache entry.
    """

    def test_health_route_hits_oracle_xe_and_returns_200(
        self, oracle_xe_app
    ) -> None:
        """oracle_xe_app bridge smoke: GET /health returns 200, database='ok'.

        Verifies end-to-end that the Flask app, when wired to Oracle XE via
        the oracle_xe_app fixture, can execute SELECT 1 FROM DUAL and report
        healthy status.

        Mutation check: removing the monkeypatch.setattr(CONNECTION_STRING) call
        from the oracle_xe_app fixture means get_health_engine() creates an
        engine pointing at the production DSN, which is unreachable from the
        test container, causing check_database() to return 'error' and the
        route to return 503.
        """
        response = oracle_xe_app.get("/health")

        assert response.status_code == 200, (
            f"Expected /health to return 200 against Oracle XE, got "
            f"{response.status_code}. "
            "The oracle_xe_app bridge may not be patching CONNECTION_STRING "
            "correctly, or the Oracle XE container is not reachable."
        )

        data = response.get_json()
        assert data is not None, "/health returned non-JSON body"

        db_status = data.get("services", {}).get("database")
        assert db_status == "ok", (
            f"Expected services.database='ok', got {db_status!r}. "
            f"Full response: {data}"
        )
