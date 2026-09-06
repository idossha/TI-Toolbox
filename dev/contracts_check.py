#!/usr/bin/env python3
"""CI superset gate: the server's dumped OpenAPI must cover the contract.

Usage::

    python dev/contracts_check.py [contracts/openapi.v0.yaml] [contracts/openapi.json]

Every ``path + method`` (with its response codes and parameters) of the
contract must exist in the dump, and every ``required`` property of each
contract schema (recursively, through ``$ref`` / nested objects / array
items) must exist in the server's schema for the same response.  For every
property the contract declares, its ``type`` and ``enum`` must match the
dump's (``anyOf`` unions and ``const`` are normalised).  Extra paths and
properties in the dump are fine.  Exit 1 on any missing or mismatching item.

A few classes of contract-vs-dump difference are *not* real drift and are
handled specially (ra_13 finding 3, worked out with F1a):

- Path parameters are compared after normalising known name aliases (the
  contract always spells a resource id ``{id}``; some server route functions
  use ``{job_id}`` / ``{report_id}`` for readability) -- see
  ``_PATH_PARAM_ALIASES`` and the top-level description in
  ``contracts/openapi.v1.yaml``.
- ``/ws/*`` paths are required in the contract but exempt from the dump
  check: FastAPI does not describe WebSocket routes in its generated
  OpenAPI document at all, so a dump can never "contain" them.
- Response codes 401/403/404 are implied by the contract's global auth/jail
  note (see its top-level ``description`` and each tag's) and are skipped
  rather than required verbatim on every operation.
- A dump response schema with no declared ``properties`` at all (FastAPI's
  shape for a route typed ``-> dict[str, Any]`` / ``-> list[dict]``) cannot
  be checked structurally; its required-property gaps are counted as
  *warnings*, not failures, and printed separately so they stay visible
  without failing the gate.
- ``PipelineConfig`` is a contract-only documentation union (the real
  discriminant is the ``kind``/path parameter, not a field on a response
  object) with no corresponding named model on the server; it is exempt
  from the named-schema-by-name check.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO / "contracts" / "openapi.v0.yaml"
DEFAULT_DUMP = REPO / "contracts" / "openapi.json"

METHODS = ("get", "post", "put", "patch", "delete")

# ra_13 finding 3a: the contract names every resource-scoped path parameter ``id``; some
# server route functions spell it ``job_id`` / ``report_id`` for readability. Treat them as
# the same parameter when comparing paths and parameter lists.
_PATH_PARAM_ALIASES = {"job_id": "id", "report_id": "id"}

# ra_13 finding 3b: FastAPI cannot describe WebSocket routes in OpenAPI at all.
_DUMP_EXEMPT_PATH_PREFIXES = ("/ws/",)

# ra_13 finding 3c: implied by the contract's global auth/jail note.
_DUMP_EXEMPT_STATUS = {"401", "403", "404"}

# ra_13 finding 3j: contract-only documentation union, no server-side named model.
_DUMP_EXEMPT_SCHEMAS = {"PipelineConfig"}

_PATH_PARAM_RE = re.compile(r"\{([^}]+)\}")


def _canonical_param_name(name: str, location: str | None) -> str:
    """Path-parameter names are compared through the alias map; other kinds verbatim."""
    if location == "path":
        return _PATH_PARAM_ALIASES.get(name, name)
    return name


def _normalize_path_template(path: str) -> str:
    """Rewrite every ``{param}`` segment through the alias map for path-level comparison."""

    def _sub(match: "re.Match[str]") -> str:
        return "{" + _PATH_PARAM_ALIASES.get(match.group(1), match.group(1)) + "}"

    return _PATH_PARAM_RE.sub(_sub, path)


def deref(doc: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Follow ``$ref`` (local only) until a concrete schema is reached."""
    seen: set[str] = set()
    while "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            break
        seen.add(ref)
        node: Any = doc
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        schema = node
    return schema


def _properties(doc: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Properties of a schema, merging ``allOf`` / ``anyOf`` / ``oneOf`` members."""
    schema = deref(doc, schema)
    props = dict(schema.get("properties", {}))
    for key in ("allOf", "anyOf", "oneOf"):
        for member in schema.get(key, []):
            props.update(_properties(doc, member))
    return props


def _types(doc: dict[str, Any], schema: dict[str, Any]) -> set[str]:
    """JSON types of a schema; ``type: [a, b]`` and ``anyOf``/``oneOf`` unions flattened."""
    schema = deref(doc, schema)
    declared = schema.get("type")
    types: set[str] = set()
    if isinstance(declared, str):
        types.add(declared)
    elif isinstance(declared, list):
        types.update(declared)
    for key in ("anyOf", "oneOf"):
        for member in schema.get(key, []):
            types.update(_types(doc, member))
    return types


def _enum(doc: dict[str, Any], schema: dict[str, Any]) -> list[Any] | None:
    """Enum values of a schema (``const: x`` counts as ``enum: [x]``), sorted."""
    schema = deref(doc, schema)
    if "enum" in schema:
        return sorted(schema["enum"], key=repr)
    if "const" in schema:
        return [schema["const"]]
    return None


def _items(doc: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any] | None:
    schema = deref(doc, schema)
    if "items" in schema:
        return schema["items"]
    for key in ("allOf", "anyOf", "oneOf"):
        for member in schema.get(key, []):
            found = _items(doc, member)
            if found is not None:
                return found
    return None


def compare_schema(
    contract: dict[str, Any],
    c_schema: dict[str, Any],
    dump: dict[str, Any],
    d_schema: dict[str, Any] | None,
    where: str,
    missing: list[str],
    warnings: list[str],
) -> None:
    c_schema = deref(contract, c_schema)
    if d_schema is None:
        missing.append(f"{where}: no schema in dump")
        return
    d_schema = deref(dump, d_schema)
    c_types = _types(contract, c_schema)
    d_types = _types(dump, d_schema)
    if c_types and d_types and c_types != d_types:
        missing.append(
            f"{where}: type {sorted(c_types)} in contract, {sorted(d_types)} in dump"
        )
    c_enum = _enum(contract, c_schema)
    if c_enum is not None and c_enum != _enum(dump, d_schema):
        missing.append(
            f"{where}: enum {c_enum} in contract, {_enum(dump, d_schema)} in dump"
        )
    c_props = _properties(contract, c_schema)
    d_props = _properties(dump, d_schema)
    # ra_13 finding 3d: a dump schema with no declared `properties` at all is FastAPI's shape
    # for a route typed `-> dict[str, Any]` / `-> list[dict]` -- there is nothing structural to
    # verify, so its required-property gaps are warnings, not failures.
    structured = "properties" in d_schema
    for name in c_schema.get("required", []):
        if name not in d_props:
            if structured:
                missing.append(f"{where}: required property '{name}' missing")
            else:
                warnings.append(
                    f"{where}: required property '{name}' missing "
                    "(dump response has no declared schema -- dict/list response)"
                )
    for name, c_prop in c_props.items():
        if name not in d_props:
            continue
        compare_schema(
            contract, c_prop, dump, d_props[name], f"{where}.{name}", missing, warnings
        )
    c_items = _items(contract, c_schema)
    if c_items is not None:
        compare_schema(
            contract,
            c_items,
            dump,
            _items(dump, d_schema),
            f"{where}[]",
            missing,
            warnings,
        )


def _response_schema(op: dict[str, Any], status: str) -> dict[str, Any] | None:
    response = op.get("responses", {}).get(status)
    if not response:
        return None
    content = response.get("content", {})
    json_body = content.get("application/json")
    return json_body.get("schema") if json_body else None


def check(
    contract: dict[str, Any], dump: dict[str, Any]
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    warnings: list[str] = []
    d_paths_by_norm = {
        _normalize_path_template(p): item for p, item in dump.get("paths", {}).items()
    }
    for path, c_item in contract.get("paths", {}).items():
        if path.startswith(_DUMP_EXEMPT_PATH_PREFIXES):
            # ra_13 finding 3b: required in the contract, but FastAPI cannot describe
            # WebSocket routes in OpenAPI, so there is nothing to compare against.
            continue
        d_item = d_paths_by_norm.get(_normalize_path_template(path))
        if d_item is None:
            missing.append(f"path {path} missing")
            continue
        for method in METHODS:
            if method not in c_item:
                continue
            if method not in d_item:
                missing.append(f"{method.upper()} {path} missing")
                continue
            c_op, d_op = c_item[method], d_item[method]
            for status, response in c_op.get("responses", {}).items():
                if status in _DUMP_EXEMPT_STATUS:
                    # ra_13 finding 3c: implied by the global auth/jail note.
                    continue
                if status not in d_op.get("responses", {}):
                    missing.append(
                        f"{method.upper()} {path}: response {status} missing"
                    )
                    continue
                if "content" not in response:
                    continue
                c_schema = _response_schema(c_op, status)
                if c_schema is None:
                    continue
                compare_schema(
                    contract,
                    c_schema,
                    dump,
                    _response_schema(d_op, status),
                    f"{method.upper()} {path} {status}",
                    missing,
                    warnings,
                )
            d_params = d_op.get("parameters", [])
            for c_param in c_op.get("parameters", []):
                c_loc = c_param.get("in")
                c_name = _canonical_param_name(c_param.get("name"), c_loc)
                if not any(
                    p.get("in") == c_loc
                    and _canonical_param_name(p.get("name"), p.get("in")) == c_name
                    for p in d_params
                ):
                    missing.append(
                        f"{method.upper()} {path}: parameter {c_param.get('name')} ({c_loc}) missing"
                    )
    # Named schemas: each contract component must exist by name in the dump
    # with all required properties (recursively).
    d_components = dump.get("components", {}).get("schemas", {})
    for name, c_schema in contract.get("components", {}).get("schemas", {}).items():
        if name in _DUMP_EXEMPT_SCHEMAS:
            # ra_13 finding 3j: contract-only documentation union, no server-side named model.
            continue
        d_schema = d_components.get(name)
        if d_schema is None:
            missing.append(f"schema {name} missing from dump components")
            continue
        compare_schema(
            contract, c_schema, dump, d_schema, f"schema {name}", missing, warnings
        )
    return missing, warnings


def main(argv: list[str]) -> int:
    contract_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_CONTRACT
    dump_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_DUMP
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    dump = json.loads(dump_path.read_text(encoding="utf-8"))
    missing, warnings = check(contract, dump)
    n_paths = sum(
        1 for item in contract["paths"].values() for m in METHODS if m in item
    )
    n_schemas = len(contract.get("components", {}).get("schemas", {}))
    if warnings:
        print(f"contracts_check: {len(warnings)} warning(s) (not gate failures):")
        for line in warnings:
            print(f"  - {line}")
    if missing:
        print(f"contracts_check: {len(missing)} problem(s):")
        for line in missing:
            print(f"  - {line}")
        return 1
    print(
        f"contracts_check: OK — {n_paths} operation(s) and {n_schemas} schema(s) "
        f"from {contract_path.name} are present in {dump_path.name}"
        + (f" ({len(warnings)} warning(s) above)" if warnings else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
