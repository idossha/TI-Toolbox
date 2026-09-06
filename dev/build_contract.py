#!/usr/bin/env python3
"""Merge ``contracts/schema.json`` into an OpenAPI contract YAML.

Every ``components.schemas.<Name>`` entry in the OpenAPI document that
carries an ``x-tit-config: <ConfigName>`` marker is replaced by the
corresponding ``schema.json`` ``$defs`` entry. Internal ``"#/$defs/X"``
refs are rewritten to ``"#/components/schemas/X"`` (or to the marker's own
key, if some other entry claims that ``$defs`` name), and every ``$defs``
entry the copied schema in turn references is copied in too, transitively.

Usage::

    python3 dev/build_contract.py [--openapi PATH] [--schema PATH] [--out PATH]

Defaults: ``contracts/openapi.v1.yaml``, ``contracts/schema.json``, and
``<openapi>`` with its suffix changed to ``.json`` (so the default input
writes ``contracts/openapi.v1.json``).

Fails with a clear, non-traceback error (exit 1) if either input file does
not exist yet -- the v1 contract and the generated schema are written by
different agents in parallel (see ``dev/notes/v3-build-plan.md`` Stage 0),
so either one may not exist yet when this runs.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OPENAPI = REPO_ROOT / "contracts" / "openapi.v1.yaml"
DEFAULT_SCHEMA = REPO_ROOT / "contracts" / "schema.json"

_DEFS_REF_PREFIX = "#/$defs/"


def _rewrite_refs(node: Any, rename: dict[str, str]) -> None:
    """In place: ``"#/$defs/<old>"`` -> ``"#/components/schemas/<rename[old] or old>"``."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_DEFS_REF_PREFIX):
            name = ref[len(_DEFS_REF_PREFIX) :]
            node["$ref"] = f"#/components/schemas/{rename.get(name, name)}"
        for value in node.values():
            _rewrite_refs(value, rename)
    elif isinstance(node, list):
        for item in node:
            _rewrite_refs(item, rename)


def _referenced_defs_names(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_DEFS_REF_PREFIX):
            out.add(ref[len(_DEFS_REF_PREFIX) :])
        for value in node.values():
            _referenced_defs_names(value, out)
    elif isinstance(node, list):
        for item in node:
            _referenced_defs_names(item, out)


def _type_const(defs_name: str, defs: dict) -> str | None:
    """The ``"_type"`` discriminator literal a ``$defs`` entry's schema carries, if any."""
    body = defs.get(defs_name)
    if not isinstance(body, dict):
        return None
    const = body.get("properties", {}).get("_type", {}).get("const")
    return const if isinstance(const, str) else None


def _add_discriminator_mappings(node: Any, type_by_key: dict[str, str]) -> None:
    """In place: for every ``oneOf`` + ``discriminator: {propertyName: "_type"}`` node, add
    ``discriminator.mapping`` from each branch's real ``"_type"`` const to its ``$ref``.

    Without this, ``openapi-typescript`` synthesises discriminant literals from ``$defs`` names
    instead of reading the schema's actual ``_type`` const, producing the wrong literal type for
    every discriminated union in the generated TS (P4 finding).
    """
    if isinstance(node, dict):
        one_of = node.get("oneOf")
        discriminator = node.get("discriminator")
        if (
            isinstance(one_of, list)
            and isinstance(discriminator, dict)
            and discriminator.get("propertyName") == "_type"
        ):
            mapping: dict[str, str] = {}
            for branch in one_of:
                if not isinstance(branch, dict):
                    continue
                ref = branch.get("$ref")
                if not isinstance(ref, str):
                    continue
                key = ref.rsplit("/", 1)[-1]
                type_const = type_by_key.get(key)
                if type_const is not None:
                    mapping[type_const] = ref
            if mapping:
                discriminator["mapping"] = mapping
        for value in node.values():
            _add_discriminator_mappings(value, type_by_key)
    elif isinstance(node, list):
        for item in node:
            _add_discriminator_mappings(item, type_by_key)


def merge(openapi: dict, schema_doc: dict) -> dict:
    """Replace every ``x-tit-config``-marked schema with its generated body.

    Parameters
    ----------
    openapi : dict
        Parsed ``contracts/openapi.v1.yaml``. Mutated in place and returned.
    schema_doc : dict
        Parsed ``contracts/schema.json`` (``{"$defs": ..., ...}``).

    Returns
    -------
    dict
        *openapi*, with every marked schema replaced (unchanged if no marker is present
        anywhere), and a ``discriminator.mapping`` added to every copied-in ``oneOf`` that
        discriminates on ``"_type"``.

    Raises
    ------
    KeyError
        If a marker names a ``$defs`` entry that does not exist.
    """
    defs = schema_doc.get("$defs", {})
    schemas = openapi.setdefault("components", {}).setdefault("schemas", {})

    # schema-key -> config-name, for every entry carrying the marker.
    markers = {
        schema_name: body["x-tit-config"]
        for schema_name, body in schemas.items()
        if isinstance(body, dict) and "x-tit-config" in body
    }
    if not markers:
        return openapi

    # A $defs entry keeps its own name in components.schemas unless a
    # marker claims that exact name under a different schema key.
    rename = {config_name: schema_name for schema_name, config_name in markers.items()}
    type_by_key: dict[str, str] = {}

    def copy_in(defs_name: str, target_key: str) -> None:
        if defs_name not in defs:
            raise KeyError(
                f"contracts/schema.json has no $defs entry {defs_name!r} "
                f"(known: {sorted(defs)})"
            )
        body = copy.deepcopy(defs[defs_name])
        referenced: set[str] = set()
        _referenced_defs_names(defs[defs_name], referenced)
        _rewrite_refs(body, rename)
        schemas[target_key] = body
        type_const = _type_const(defs_name, defs)
        if type_const is not None:
            type_by_key[target_key] = type_const
        # `sorted`, not the set's own order: set-of-str iteration order depends on
        # PYTHONHASHSEED, and this loop decides the insertion order of
        # ``components.schemas``. Without it every rebuild reshuffles a few hundred
        # lines of the generated JSON and the file's diff says nothing.
        for ref_name in sorted(referenced - copied):
            copied.add(ref_name)
            copy_in(ref_name, rename.get(ref_name, ref_name))

    copied: set[str] = set(markers.values())
    for schema_name, config_name in markers.items():
        copy_in(config_name, schema_name)

    _add_discriminator_mappings(schemas, type_by_key)

    return openapi


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openapi", type=Path, default=DEFAULT_OPENAPI)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.openapi.is_file():
        print(
            f"error: {args.openapi} does not exist yet -- this runs after the "
            "v1 contract has been authored (dev/notes/v3-build-plan.md Stage 0).",
            file=sys.stderr,
        )
        return 1
    if not args.schema.is_file():
        print(
            f"error: {args.schema} does not exist yet -- run "
            "`python3 dev/build_schema.py` first.",
            file=sys.stderr,
        )
        return 1

    openapi = yaml.safe_load(args.openapi.read_text())
    schema_doc = json.loads(args.schema.read_text())
    merged = merge(openapi, schema_doc)

    out_path = args.out or args.openapi.with_suffix(".json")
    out_path.write_text(json.dumps(merged, indent=2, sort_keys=False) + "\n")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
