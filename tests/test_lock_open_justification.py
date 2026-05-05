# -*- coding: utf-8 -*-
"""Static check: every fail_mode="open" call site must carry a justification comment.

Walks every .py file under src/mes_dashboard/, finds lines containing
fail_mode="open" or fail_mode='open', and asserts that the same line OR
the line directly above contains the substring 'fail_mode=open:'.

This test passes vacuously today (zero open sites) and acts as a guardrail
against future callers opting in without a comment.
"""

from __future__ import annotations

import re
from pathlib import Path


_SRC_ROOT = Path(__file__).parent.parent / "src" / "mes_dashboard"

_OPEN_PATTERN = re.compile(r"""fail_mode\s*=\s*["']open["']""")
_JUSTIFICATION_PATTERN = re.compile(r"fail_mode=open:")


def _is_code_line(line: str) -> bool:
    """Return True only if the line looks like executable Python code.

    Lines that are comments, docstring text, or rst/backtick snippets are
    excluded — those are documentation, not call sites.
    """
    stripped = line.strip()
    # Pure comment lines
    if stripped.startswith("#"):
        return False
    # Lines inside docstrings that are not assignments/calls:
    # A code call site always has fail_mode= outside a quoted string context.
    # We detect documentation lines by checking for rst backticks or leading
    # triple-quote context markers.
    if "``fail_mode" in line or stripped.startswith('"""') or stripped.startswith("'''"):
        return False
    # If the fail_mode= appears inside a quoted string (after a " or '), skip.
    # Heuristic: if the character before the match in the stripped line is a
    # space or opening paren, it's a kwarg; if it's part of narrative prose, skip.
    return True


def _collect_unjustified_open_sites():
    violations = []
    for py_file in sorted(_SRC_ROOT.rglob("*.py")):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if _OPEN_PATTERN.search(line) and _is_code_line(line):
                # Check this line and the line above for the justification comment
                prev_line = lines[lineno - 2] if lineno >= 2 else ""
                if not (
                    _JUSTIFICATION_PATTERN.search(line)
                    or _JUSTIFICATION_PATTERN.search(prev_line)
                ):
                    violations.append(
                        f"{py_file.relative_to(_SRC_ROOT.parent.parent)}:{lineno}: "
                        f"fail_mode='open' without justification comment"
                    )
    return violations


def test_open_fail_mode_sites_have_justification_comment():
    """Every fail_mode='open' site must carry a 'fail_mode=open: <reason>' comment."""
    violations = _collect_unjustified_open_sites()
    assert violations == [], (
        "Found fail_mode='open' sites without a justification comment.\n"
        "Add '# fail_mode=open: <reason>' on the same line or the line above.\n"
        "Violations:\n" + "\n".join(f"  {v}" for v in violations)
    )
