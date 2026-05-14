"""Property: cross-filter selection order is irrelevant (PHF-01, AC-2).

For any cached 4-tuple corpus and any selection dict `{pj_types, packages,
bops, pj_functions}`:

    get_filter_options({A: x, B: y})  ==  get_filter_options({B: y, A: x})

The ordering of keys in the selection dict cannot influence the result —
the underlying single-pass tuple scan is order-independent by design.

We seed the cache with a synthetic 4-tuple corpus (no Oracle) and run 50
deterministic permutations of pairwise selections plus randomised
Hypothesis cases.
"""

from __future__ import annotations

import random
from typing import List, Tuple

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import mes_dashboard.services.container_filter_cache as cfc


# Synthetic 4-tuple corpus: small but enough that selections produce non-trivial
# narrowing. Each tuple is (pj_type, package, bop, pj_function|None).
_SYNTHETIC_TUPLES: List[Tuple[str, str, str, str]] = [
    ("TYPE_A", "PKG_1", "BOP_X", "FN_alpha"),
    ("TYPE_A", "PKG_1", "BOP_Y", "FN_beta"),
    ("TYPE_A", "PKG_2", "BOP_X", "FN_alpha"),
    ("TYPE_B", "PKG_1", "BOP_X", "FN_gamma"),
    ("TYPE_B", "PKG_2", "BOP_Y", ""),         # PJ_FUNCTION nullable
    ("TYPE_B", "PKG_3", "BOP_Z", "FN_alpha"),
    ("TYPE_C", "PKG_3", "BOP_Z", "FN_delta"),
    ("TYPE_C", "PKG_1", "BOP_X", "FN_alpha"),
]


def _seed_cache(tuples: List[Tuple[str, str, str, str]]) -> None:
    """Directly populate container_filter_cache._CACHE without Oracle.

    Mirrors the structure built by `_load_from_oracle` so `get_filter_options`
    operates on a known corpus.
    """
    pj_types = sorted({t[0] for t in tuples})
    packages = sorted({t[1] for t in tuples})
    bops = sorted({t[2] for t in tuples})
    pj_functions = sorted({t[3] for t in tuples if t[3]})

    with cfc._CACHE_LOCK:
        cfc._CACHE["tuples"] = list(tuples)
        cfc._CACHE["indices"] = {
            "pj_types": pj_types,
            "packages": packages,
            "bops": bops,
            "pj_functions": pj_functions,
        }
        cfc._CACHE["updated_at"] = "2026-05-14T00:00:00Z"
        cfc._CACHE["schema_version"] = cfc.SCHEMA_VERSION
        cfc._CACHE["loaded"] = True


@pytest.fixture(autouse=True)
def _seed_synthetic_cache():
    """Seed cache + restore original state after each test."""
    with cfc._CACHE_LOCK:
        original = {
            "tuples": list(cfc._CACHE.get("tuples") or []),
            "indices": dict(cfc._CACHE.get("indices") or {}),
            "updated_at": cfc._CACHE.get("updated_at"),
            "schema_version": cfc._CACHE.get("schema_version"),
            "loaded": cfc._CACHE.get("loaded"),
        }
    _seed_cache(_SYNTHETIC_TUPLES)
    yield
    with cfc._CACHE_LOCK:
        for k, v in original.items():
            cfc._CACHE[k] = v


def _normalise_result(result: dict) -> dict:
    """Strip volatile fields (updated_at) so equality is value-only."""
    return {
        "pj_types": sorted(result.get("pj_types") or []),
        "packages": sorted(result.get("packages") or []),
        "bops": sorted(result.get("bops") or []),
        "pj_functions": sorted(result.get("pj_functions") or []),
    }


# Deterministic seed for parametrised order-independence cases.
_RNG = random.Random(0xC0FFEE)


def _gen_selections(n: int = 50):
    """Generate 50 paired (dict_A, dict_B) where dict_B has reversed key order."""
    cases = []
    keys = ["pj_types", "packages", "bops", "pj_functions"]
    domains = {
        "pj_types": ["TYPE_A", "TYPE_B", "TYPE_C"],
        "packages": ["PKG_1", "PKG_2", "PKG_3"],
        "bops": ["BOP_X", "BOP_Y", "BOP_Z"],
        "pj_functions": ["FN_alpha", "FN_beta", "FN_gamma", "FN_delta"],
    }
    for _ in range(n):
        chosen = _RNG.sample(keys, k=_RNG.randint(1, 4))
        sel = {}
        for k in chosen:
            sel[k] = _RNG.sample(domains[k], k=_RNG.randint(1, len(domains[k])))
        # Build the reverse-key-order variant.
        reversed_sel = dict(reversed(list(sel.items())))
        cases.append((sel, reversed_sel))
    return cases


@pytest.mark.parametrize("forward,reversed_keys", _gen_selections(50))
def test_cross_filter_selection_key_order_independence(forward, reversed_keys):
    """50 deterministic key-order permutations — same selections, same answer."""
    a = cfc.get_filter_options(forward)
    b = cfc.get_filter_options(reversed_keys)
    assert _normalise_result(a) == _normalise_result(b), (
        f"cross-filter results differed by key order:\n  "
        f"forward={forward}\n  reversed={reversed_keys}\n  "
        f"a={_normalise_result(a)}\n  b={_normalise_result(b)}"
    )


# Hypothesis property: same selection set → same result, regardless of how it's
# constructed (key order, list order within a value, duplicate values).
_field_values = {
    "pj_types": st.sampled_from(["TYPE_A", "TYPE_B", "TYPE_C", "TYPE_UNKNOWN"]),
    "packages": st.sampled_from(["PKG_1", "PKG_2", "PKG_3", "PKG_UNKNOWN"]),
    "bops": st.sampled_from(["BOP_X", "BOP_Y", "BOP_Z", "BOP_UNKNOWN"]),
    "pj_functions": st.sampled_from(["FN_alpha", "FN_beta", "FN_gamma", "FN_delta", "FN_UNKNOWN"]),
}

_selection_dict = st.fixed_dictionaries(
    {},
    optional={
        k: st.lists(v, min_size=0, max_size=4)
        for k, v in _field_values.items()
    },
)


@pytest.mark.property
@given(sel=_selection_dict)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
def test_cross_filter_value_order_independence(sel):
    """Same selection, value list reversed → same result."""
    a = cfc.get_filter_options(sel)
    reversed_values = {k: list(reversed(v)) for k, v in sel.items()}
    b = cfc.get_filter_options(reversed_values)
    assert _normalise_result(a) == _normalise_result(b), (
        f"value order matters! sel={sel}, reversed={reversed_values}, "
        f"a={a}, b={b}"
    )


@pytest.mark.property
@given(sel=_selection_dict)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
def test_cross_filter_duplicate_values_idempotent(sel):
    """Duplicating a selection value MUST NOT change the result."""
    a = cfc.get_filter_options(sel)
    doubled = {k: list(v) + list(v) for k, v in sel.items()}
    b = cfc.get_filter_options(doubled)
    assert _normalise_result(a) == _normalise_result(b)
