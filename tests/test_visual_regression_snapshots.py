# -*- coding: utf-8 -*-
"""Visual regression snapshot contract checks for migration-critical states."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_FILE = (
    ROOT / "docs" / "migration" / "portal-shell-route-view-integration" / "visual-regression-snapshots.json"
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compute_fingerprint(files: list[str]) -> str:
    lines: list[str] = []
    for rel in files:
        path = ROOT / rel
        assert path.exists(), f"snapshot file missing: {rel}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(rel)
        lines.append(digest)
    payload = "\n".join(lines) + "\n"
    return _sha256_text(payload)


def test_visual_snapshot_policy_blocks_release_on_critical_diff():
    payload = _read_json(SNAPSHOT_FILE)
    policy = payload["critical_diff_policy"]
    assert policy["block_release"] is True
    assert policy["severity"] == "critical"


def test_visual_snapshot_fingerprints_match_current_sources():
    payload = _read_json(SNAPSHOT_FILE)
    snapshots = payload.get("snapshots", [])
    assert snapshots, "no visual snapshot entries"

    for item in snapshots:
        files = item.get("files", [])
        expected = str(item.get("fingerprint", "")).strip()
        assert files and expected, f"invalid snapshot entry: {item.get('id')}"

        actual = _compute_fingerprint(files)
        assert actual == expected, f"critical visual snapshot diff: {item.get('id')}"
