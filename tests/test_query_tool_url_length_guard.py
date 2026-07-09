# -*- coding: utf-8 -*-
"""URL-length invariant for the query-tool GET batch routes.

The lot-history / lot-associations routes accept a comma-joined list of up to
``QUERY_TOOL_MAX_CONTAINER_IDS`` container IDs in the request query string. If a
worst-case batch produces a request line longer than gunicorn's
``limit_request_line``, gunicorn rejects it with a bare 414 *before* the app's
clean 413 batch-size guard runs — a confusing failure for the user.

This test pins the invariant that a worst-case batch fits comfortably within the
configured ``limit_request_line``. It fails if someone raises the container-id
cap, lowers the gunicorn limit, or the (assumed) container-id length grows beyond
what the ceiling can hold — at which point those routes should move to POST
(see ``frontend/src/core/post-export.ts``).
"""

import importlib.util
import os
import sys


# Conservative upper bound for a single MES CONTAINERID in the request string.
# Real IDs observed in fixtures look like ``GA25010001-A01`` (~14 chars); 32 gives
# well over 2x headroom while keeping the invariant meaningful.
CONTAINER_ID_MAX_LEN = 32

# Longest query-tool GET path that carries a container_ids batch.
_LOT_HISTORY_PATH = "/api/query-tool/lot-history"


def _load_gunicorn_conf():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    original_path = sys.path[:]
    try:
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        spec = importlib.util.spec_from_file_location(
            "gunicorn_conf",
            os.path.join(repo_root, "gunicorn.conf.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path[:] = original_path


def _default_max_container_ids():
    """QUERY_TOOL_MAX_CONTAINER_IDS default, read from the route module."""
    from mes_dashboard import create_app
    from mes_dashboard.routes import query_tool_routes

    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        return query_tool_routes._query_tool_max_container_ids()


def _worst_case_request_line(num_ids: int) -> int:
    """Bytes in the HTTP request line for a full lot-history batch GET."""
    ids = ",".join("C" * CONTAINER_ID_MAX_LEN for _ in range(num_ids))
    query = (
        f"container_ids={ids}"
        "&page=999999"
        "&per_page=1000"
        "&workcenter_groups=WORKCENTER-GROUP-A,WORKCENTER-GROUP-B"
    )
    # "GET <path>?<query> HTTP/1.1"
    return len("GET ") + len(_LOT_HISTORY_PATH) + 1 + len(query) + len(" HTTP/1.1")


def test_gunicorn_sets_explicit_request_line_limit():
    """limit_request_line must be set explicitly, not left to the 4094 default."""
    conf = _load_gunicorn_conf()
    assert hasattr(conf, "limit_request_line"), (
        "gunicorn.conf.py must set limit_request_line explicitly so the "
        "query-tool GET batch URL length does not silently rely on the 4094 default"
    )
    # gunicorn requires 0 <= limit_request_line <= 8190 (0 = unlimited).
    assert 0 <= conf.limit_request_line <= 8190


def test_worst_case_batch_get_fits_within_request_line_limit():
    conf = _load_gunicorn_conf()
    limit = conf.limit_request_line
    max_ids = _default_max_container_ids()

    worst_case = _worst_case_request_line(max_ids)

    assert limit == 0 or worst_case <= limit, (
        f"A worst-case lot-history GET with {max_ids} container IDs is "
        f"{worst_case} bytes, exceeding gunicorn limit_request_line={limit}. "
        "Lower QUERY_TOOL_MAX_CONTAINER_IDS, raise the limit (<=8190), or move "
        "the batch routes to POST."
    )


def test_current_default_cap_is_covered_by_default_limit():
    """The shipped defaults (cap=200, limit=8190) must satisfy the invariant with
    headroom — a regression tripwire independent of env overrides."""
    worst_case = _worst_case_request_line(200)
    assert worst_case <= 8190, (
        f"Default 200-ID worst-case GET is {worst_case} bytes; the default "
        "limit_request_line of 8190 no longer covers it."
    )
