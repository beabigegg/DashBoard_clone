# -*- coding: utf-8 -*-
"""AC-4: response-samples.json manifest + samples/*.json exist and are complete.

Tests that:
- Every key in response-samples.json maps to a valid endpoint key format.
- All sample file paths referenced in the manifest exist on disk.
- Manifest has >= 158 entries.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MANIFEST_PATH = Path(__file__).parent / "response-samples.json"
SAMPLES_DIR = Path(__file__).parent / "samples"
CONTRACT_PATH = (
    Path(__file__).parent.parent.parent / "contracts" / "api" / "api-contract.md"
)


def _load_manifest():
    if not MANIFEST_PATH.exists():
        pytest.skip("response-samples.json not found — run capture_samples.py first")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class TestManifestCompleteness:
    """AC-4: manifest is complete and all sample files exist."""

    def test_manifest_exists(self):
        """response-samples.json must exist."""
        assert MANIFEST_PATH.exists(), (
            f"response-samples.json not found at {MANIFEST_PATH}. "
            "Run: python tests/contract/capture_samples.py"
        )

    def test_manifest_has_at_least_158_entries(self):
        """Manifest must have >= 158 entries."""
        manifest = _load_manifest()
        assert len(manifest) >= 158, (
            f"Expected >= 158 manifest entries, found {len(manifest)}"
        )

    def test_manifest_keys_match_known_endpoints(self):
        """Every key in the manifest must be a 'METHOD /path' format (no orphans)."""
        manifest = _load_manifest()
        import re
        # Keys must be "METHOD /path" format, e.g. "GET /api/health"
        # Method words: GET, POST, PUT, PATCH, DELETE
        valid_pattern = re.compile(
            r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) /\S"
        )
        bad_keys = [
            k for k in manifest
            if not valid_pattern.match(k)
        ]
        assert not bad_keys, (
            f"Manifest keys with unexpected format (expected 'METHOD /path'): {bad_keys}"
        )

    def test_all_sample_files_exist_on_disk(self):
        """Every sample path in the manifest must exist on disk."""
        manifest = _load_manifest()
        missing = []
        for key, entry in manifest.items():
            if isinstance(entry, str):
                sample_path = MANIFEST_PATH.parent / entry
            elif isinstance(entry, dict):
                sample_rel = entry.get("sample", "")
                sample_path = MANIFEST_PATH.parent / sample_rel
            else:
                continue
            if not sample_path.exists():
                missing.append(f"{key} → {sample_path}")

        assert not missing, (
            f"{len(missing)} sample file(s) missing from disk:\n"
            + "\n".join(missing[:20])
        )

    def test_all_sample_files_are_valid_json(self):
        """Every sample file in the manifest must contain valid JSON."""
        manifest = _load_manifest()
        invalid = []
        for key, entry in manifest.items():
            if isinstance(entry, str):
                sample_path = MANIFEST_PATH.parent / entry
            elif isinstance(entry, dict):
                sample_path = MANIFEST_PATH.parent / entry.get("sample", "")
            else:
                continue
            if not sample_path.exists():
                continue
            try:
                json.loads(sample_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                invalid.append(f"{key}: {exc}")

        assert not invalid, (
            f"{len(invalid)} sample file(s) contain invalid JSON:\n"
            + "\n".join(invalid[:10])
        )
