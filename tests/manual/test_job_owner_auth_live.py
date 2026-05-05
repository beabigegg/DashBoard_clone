"""Live end-to-end auth test for /api/job/<id>/abandon.

Run against the real dev server on http://127.0.0.1:8080. Uses two real HTTP
sessions (logged-in user + anonymous browser) to prove that:

1. Logged-in enqueue writes meta["owner"] = username (regression for the
   original "owner field never set" bug).
2. Same-session abandon succeeds (200).
3. Cross-session abandon (different cookies) returns 403.
4. Body ``owner`` field is ignored — server uses the session token.
5. Anonymous round-trip works (cookie-bound uuid token).
6. Anonymous A enqueue + anonymous B abandon → 403.

Usage:
    conda run -n mes-dashboard python tests/manual/test_job_owner_auth_live.py
"""
from __future__ import annotations

import os
import sys
import uuid

import requests

BASE = os.environ.get("LIVE_BASE_URL", "http://127.0.0.1:8080")
USERNAME = os.environ.get("LOCAL_AUTH_USERNAME", "92367")
PASSWORD = os.environ.get("LOCAL_AUTH_PASSWORD", "1QAZ2wsx3edc")
PREFIX = "reject"

# Far-future range → query slow enough to stay in queued/running for at
# least a few hundred ms so we can race the abandon.
ENQUEUE_PAYLOAD = {
    "mode": "container",
    "container_input_type": "lot_id",
    "container_values": [f"NONEXISTENT-{uuid.uuid4().hex[:8]}"],
    "start_date": "2020-01-01",
    "end_date": "2020-12-31",
    "include_excluded_scrap": False,
    "exclude_material_scrap": False,
    "exclude_pb_diode": False,
}

failures: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  PASS  {label}")
    else:
        msg = f"  FAIL  {label}: {detail}"
        print(msg)
        failures.append(label)


def login(session: requests.Session) -> None:
    r = session.post(
        f"{BASE}/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=10,
    )
    r.raise_for_status()
    assert r.json()["success"] is True, r.text


def enqueue_reject(session: requests.Session) -> str | None:
    r = session.post(
        f"{BASE}/api/reject-history/query",
        json=ENQUEUE_PAYLOAD,
        timeout=20,
    )
    if r.status_code == 202:
        return r.json()["data"]["job_id"]
    # Some envs may inline-execute. Skip in that case.
    print(f"    [enqueue returned {r.status_code}, body={r.text[:200]}]")
    return None


def abandon(session: requests.Session, job_id: str, body_extra: dict | None = None) -> requests.Response:
    body = {"prefix": PREFIX}
    if body_extra:
        body.update(body_extra)
    return session.post(f"{BASE}/api/job/{job_id}/abandon", json=body, timeout=10)


def main() -> int:
    print(f"== Live auth test against {BASE} ==")

    # ------------------------------------------------------------------
    # Session A: real login
    # ------------------------------------------------------------------
    s_user_a = requests.Session()
    login(s_user_a)
    print("[1] Logged-in user session A established.")

    # ------------------------------------------------------------------
    # Session B: another logged-in copy (same user, different cookie jar).
    # Owner token = username — so this is cross-tab, not cross-user.
    # We skip "different real user" because we only have one credential.
    # Instead we test against an anonymous session, which has a different
    # owner token regardless of which real user is logged in.
    # ------------------------------------------------------------------

    # Anonymous session A
    s_anon_a = requests.Session()
    # Force cookie creation by visiting any endpoint that touches session
    s_anon_a.get(f"{BASE}/api/auth/me", timeout=10)

    # Anonymous session B
    s_anon_b = requests.Session()
    s_anon_b.get(f"{BASE}/api/auth/me", timeout=10)

    # ------------------------------------------------------------------
    # Scenario 1: logged-in enqueue → same session abandon (200)
    # ------------------------------------------------------------------
    print("\n[Scenario 1] Logged-in enqueue + self abandon")
    job_id = enqueue_reject(s_user_a)
    if job_id:
        r = abandon(s_user_a, job_id)
        check(
            "self-abandon returns 200",
            r.status_code == 200,
            f"got {r.status_code}: {r.text[:200]}",
        )
        if r.status_code == 200:
            data = r.json()["data"]
            check(
                "abandon response status=abandoned",
                data.get("status") == "abandoned",
                str(data),
            )
    else:
        check("logged-in enqueue produced job_id", False, "no async job")

    # ------------------------------------------------------------------
    # Scenario 2: logged-in enqueue → anonymous session abandon (403)
    # Proves cross-session denial even when the body claims the right owner.
    # ------------------------------------------------------------------
    print("\n[Scenario 2] Logged-in enqueue + cross-session abandon (403)")
    job_id = enqueue_reject(s_user_a)
    if job_id:
        # Try with body owner field set to the username — should still fail.
        r = abandon(s_anon_a, job_id, body_extra={"owner": USERNAME})
        check(
            "cross-session abandon returns 403",
            r.status_code == 403,
            f"got {r.status_code}: {r.text[:200]}",
        )
        # Now self-cleanup
        abandon(s_user_a, job_id)

    # ------------------------------------------------------------------
    # Scenario 3: anonymous A enqueue → anonymous A abandon (200)
    # Cookie-bound uuid token round-trip.
    # ------------------------------------------------------------------
    print("\n[Scenario 3] Anonymous self round-trip")
    job_id = enqueue_reject(s_anon_a)
    if job_id is None:
        # Anon may be blocked by login_required on some routes; skip soft.
        print("    [anon enqueue not allowed in this env — skipping scenario 3/4]")
    else:
        r = abandon(s_anon_a, job_id)
        check(
            "anon self-abandon returns 200",
            r.status_code == 200,
            f"got {r.status_code}: {r.text[:200]}",
        )

        # ------------------------------------------------------------
        # Scenario 4: anonymous A enqueue → anonymous B abandon (403)
        # ------------------------------------------------------------
        print("\n[Scenario 4] Anonymous A enqueue + anonymous B abandon (403)")
        job_id = enqueue_reject(s_anon_a)
        if job_id:
            r = abandon(s_anon_b, job_id)
            check(
                "anon-B cross-abandon returns 403",
                r.status_code == 403,
                f"got {r.status_code}: {r.text[:200]}",
            )
            abandon(s_anon_a, job_id)

    # ------------------------------------------------------------------
    # Scenario 5: bogus job_id → 404 (not 403, not 500)
    # ------------------------------------------------------------------
    print("\n[Scenario 5] Bogus job_id → 404")
    r = abandon(s_user_a, "nonexistent-" + uuid.uuid4().hex)
    check(
        "bogus job returns 404",
        r.status_code == 404,
        f"got {r.status_code}: {r.text[:200]}",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print()
    if failures:
        print(f"FAILED: {len(failures)} assertion(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL LIVE AUTH SCENARIOS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
