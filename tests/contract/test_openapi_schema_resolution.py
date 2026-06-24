# -*- coding: utf-8 -*-
"""AC-2: contracts/openapi.json carries resolved schemas for all endpoints.

Tests that:
- contracts/openapi.json exists and is valid JSON.
- All $ref nodes in the document resolve within the document itself.
- The HTTP operation count is >= 154 (one per endpoint; nav-config-to-code: 158 - 4 drawer + 1 PUT pages = 155, floor 154).
- At least 100 operations have response $ref linkages (not just description text).
- All $ref values in responses resolve to known component schemas.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

OPENAPI_PATH = Path(__file__).parent.parent.parent / "contracts" / "openapi.json"


def _collect_refs(obj, refs=None):
    """Recursively collect all $ref values from a JSON object."""
    if refs is None:
        refs = []
    if isinstance(obj, dict):
        if "$ref" in obj:
            refs.append(obj["$ref"])
        for v in obj.values():
            _collect_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _collect_refs(item, refs)
    return refs


def _resolve_ref(ref: str, doc: dict) -> bool:
    """Return True if a local $ref (starting with #/) resolves in the document."""
    if not ref.startswith("#/"):
        # External refs — skip (not expected in this project)
        return True
    parts = ref[2:].split("/")
    node = doc
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


class TestOpenApiSchemaResolution:
    """AC-2: contracts/openapi.json is valid and has resolved schemas."""

    def test_openapi_json_exists(self):
        """contracts/openapi.json must exist."""
        assert OPENAPI_PATH.exists(), (
            f"contracts/openapi.json not found at {OPENAPI_PATH}. "
            "Run: cdd-kit openapi export --out contracts/openapi.json"
        )

    def test_openapi_json_valid(self):
        """contracts/openapi.json must be parseable JSON."""
        content = OPENAPI_PATH.read_text(encoding="utf-8")
        try:
            doc = json.loads(content)
        except json.JSONDecodeError as exc:
            pytest.fail(f"contracts/openapi.json is not valid JSON: {exc}")

    def test_openapi_json_no_unresolved_refs(self):
        """All $ref nodes in contracts/openapi.json must resolve within the document."""
        if not OPENAPI_PATH.exists():
            pytest.skip("openapi.json not found — run cdd-kit openapi export first")

        content = OPENAPI_PATH.read_text(encoding="utf-8")
        doc = json.loads(content)
        refs = _collect_refs(doc)

        unresolved = [
            ref for ref in refs
            if ref.startswith("#/") and not _resolve_ref(ref, doc)
        ]
        assert not unresolved, (
            f"{len(unresolved)} unresolved $ref(s) in contracts/openapi.json:\n"
            + "\n".join(unresolved[:20])
        )

    def test_openapi_operation_count_at_least_154(self):
        """HTTP operation count in openapi.json must be >= 154.

        nav-config-to-code removed 4 drawer operations (GET/POST/PUT/DELETE /admin/api/drawers*)
        and added 1 PUT /admin/api/pages/{route} = net -3. Floor updated from 158 to 154 (with 1 tolerance).
        Count method+path combinations (operations) from the paths object.
        """
        if not OPENAPI_PATH.exists():
            pytest.skip("openapi.json not found — run cdd-kit openapi export first")

        content = OPENAPI_PATH.read_text(encoding="utf-8")
        doc = json.loads(content)
        paths_obj = doc.get("paths", {})
        _HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
        total_ops = sum(
            len([m for m in methods if m.lower() in _HTTP_METHODS])
            for methods in paths_obj.values()
        )
        assert total_ops >= 154, (
            f"Expected >= 154 HTTP operations in openapi.json paths, found {total_ops}. "
            "Run: cdd-kit openapi export --out contracts/openapi.json"
        )

    def test_operations_have_response_ref_linkages(self):
        """At least 100 operations must have response $ref linkages.

        After response-shape-adr0007, all JSON-returning endpoints have typed
        schemas. Endpoints returning binary/stream or redirect have no JSON schema.
        Minimum threshold: 100 (out of ~155 total post nav-config-to-code; ~14 binary/stream/redirect endpoints
        and ~2 parameterized paths that the validator normalizes differently).
        """
        if not OPENAPI_PATH.exists():
            pytest.skip("openapi.json not found — run cdd-kit openapi export first")

        content = OPENAPI_PATH.read_text(encoding="utf-8")
        doc = json.loads(content)
        paths_obj = doc.get("paths", {})
        _HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

        ops_with_ref = 0
        ops_without_ref = []
        for path, methods in paths_obj.items():
            for method, op in methods.items():
                if method.lower() not in _HTTP_METHODS:
                    continue
                has_ref = False
                for code, resp in op.get("responses", {}).items():
                    for ct, ct_val in resp.get("content", {}).items():
                        schema = ct_val.get("schema", {})
                        if "$ref" in schema:
                            has_ref = True
                            break
                    if has_ref:
                        break
                if has_ref:
                    ops_with_ref += 1
                else:
                    ops_without_ref.append(f"{method.upper()} {path}")

        assert ops_with_ref >= 100, (
            f"Expected >= 100 operations with response $ref linkages, found {ops_with_ref}.\n"
            f"Operations without $ref ({len(ops_without_ref)}):\n"
            + "\n".join(ops_without_ref[:20])
        )

    def test_response_refs_resolve_to_component_schemas(self):
        """Every response $ref must resolve to a known component schema.

        After response-shape-adr0007, component schemas include all typed schemas.
        """
        if not OPENAPI_PATH.exists():
            pytest.skip("openapi.json not found — run cdd-kit openapi export first")

        content = OPENAPI_PATH.read_text(encoding="utf-8")
        doc = json.loads(content)
        component_schemas = set(
            doc.get("components", {}).get("schemas", {}).keys()
        )
        paths_obj = doc.get("paths", {})
        _HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}

        unresolved_refs = []
        for path, methods in paths_obj.items():
            for method, op in methods.items():
                if method.lower() not in _HTTP_METHODS:
                    continue
                for code, resp in op.get("responses", {}).items():
                    for ct, ct_val in resp.get("content", {}).items():
                        schema = ct_val.get("schema", {})
                        if "$ref" in schema:
                            ref = schema["$ref"]
                            # $ref format: #/components/schemas/SchemaName
                            schema_name = ref.split("/")[-1]
                            if schema_name not in component_schemas:
                                unresolved_refs.append(
                                    f"{method.upper()} {path}: {ref}"
                                )

        assert not unresolved_refs, (
            f"{len(unresolved_refs)} response $ref(s) do not resolve to component schemas:\n"
            + "\n".join(unresolved_refs[:20]) + "\n\n"
            f"Known component schemas: {sorted(component_schemas)}"
        )
