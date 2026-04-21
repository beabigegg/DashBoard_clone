"""Reusable Hypothesis strategies for MES Dashboard property tests."""

from hypothesis import strategies as st

# ── Text ────────────────────────────────────────────────────────────────────

arbitrary_text = st.text()

short_text = st.text(max_size=50)

url_safe_text = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd"),
        whitelist_characters="-._~:/?#[]@!$&'()*+,;=%",
    ),
    max_size=256,
)

nonempty_text = st.text(min_size=1, max_size=200)

# ── Integers ────────────────────────────────────────────────────────────────

arbitrary_int = st.integers(min_value=-(2**31), max_value=2**31 - 1)

page_int = st.integers(min_value=-1000, max_value=10_000)

size_int = st.integers(min_value=-100, max_value=10_000)

# ── Sort keys ────────────────────────────────────────────────────────────────

YIELD_ALERT_VALID_SORT_KEYS = [
    "date_bucket",
    "workorder",
    "reason_code",
    "package",
    "type",
    "scrap_qty",
    "yield_pct",
    "risk_score",
]

valid_sort_key = st.sampled_from(YIELD_ALERT_VALID_SORT_KEYS)

unknown_sort_key = st.text(min_size=1, max_size=50).filter(
    lambda k: k not in YIELD_ALERT_VALID_SORT_KEYS
)

# ── Filter dicts ─────────────────────────────────────────────────────────────

_filter_key = st.sampled_from(
    ["departments", "process_category", "lines", "packages", "types", "functions"]
)

_filter_value = st.lists(st.text(max_size=40), max_size=10)

filter_dict = st.fixed_dictionaries(
    {},
    optional={
        "departments": _filter_value,
        "process_category": _filter_value,
        "lines": _filter_value,
        "packages": _filter_value,
        "types": _filter_value,
        "functions": _filter_value,
    },
)

# ── Synthetic dataset rows for filter invariant tests ─────────────────────────

_text_cell = st.text(max_size=30)

synthetic_row = st.fixed_dictionaries(
    {
        "DEPARTMENT_GROUP": _text_cell,
        "PROCESS_CATEGORY": _text_cell,
        "LINE_NAME": _text_cell,
        "PACKAGE_NAME": _text_cell,
        "TYPE_NAME": _text_cell,
        "FUNCTION_NAME": _text_cell,
    }
)

synthetic_dataset = st.lists(synthetic_row, min_size=0, max_size=50)

# ── Date strings ─────────────────────────────────────────────────────────────

valid_date_str = st.dates().map(lambda d: d.isoformat())

arbitrary_date_str = st.one_of(
    valid_date_str,
    st.text(max_size=20),
    st.just(""),
    st.just(None),
)

# ── URL query state ───────────────────────────────────────────────────────────

_tab_options = ["lot", "reverse", "equipment"]

url_state = st.fixed_dictionaries(
    {
        "tab": st.sampled_from(_tab_options),
        "lot_input_type": st.sampled_from(
            ["lot_id", "work_order", "serial_number", "gd_lot_id"]
        ),
        "lot_values": st.lists(st.text(max_size=30), max_size=5),
    },
    optional={
        "lot_sub_tab": st.sampled_from(["history", "association"]),
        "workcenter_groups": st.lists(nonempty_text, max_size=3),
    },
)
