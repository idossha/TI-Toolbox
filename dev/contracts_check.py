#!/usr/bin/env python3
"""CI gate for ``contracts/``: no generated drift, and the live server covers the contract.

Usage::

    python3 dev/contracts_check.py                   # the gate
    python3 dev/contracts_check.py --no-schema-d-ts  # a CI job where another step diffs schema.d.ts
    python3 dev/contracts_check.py --write-baseline  # after fixing (or knowingly adding) warnings

Exit 0 when everything was checked and holds, 1 on drift / a contract mismatch / a warning
count that moved off ``dev/contracts_check_baseline.json``, 2 when something could not be
checked (bad arguments, an unreadable baseline, or ``CI`` set without ``desktop/node_modules``
so ``schema.d.ts`` cannot be regenerated).

Two checks, in order.

**1. Drift.** Regenerate ``contracts/generated/config.schema.json`` and
``contracts/generated/openapi.json`` in memory and compare byte for byte
against what is committed (``dev/build_schema.py --check`` /
``dev/build_contract.py --check``).  ``desktop/src/renderer/api/schema.d.ts``
is checked the same way with ``openapi-typescript`` from ``desktop/node_modules``.
Locally, a tree without ``node_modules`` says it skipped that file; under ``CI``
the same situation exits 2 (could not check), never a silent pass -- a job that
leaves the diff to another step says so with ``--no-schema-d-ts``.  Any
difference fails with "run ``npm run gen``" -- nothing under
``contracts/generated/`` is ever hand-edited.

**2. Coverage.** Build the FastAPI app in-process and take its own OpenAPI
document (the same object ``--dump-openapi`` writes and ``GET
/api/openapi.json`` serves), then check that it covers
``contracts/openapi.yaml``.  There is no committed dump to go stale.

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
  ``contracts/openapi.yaml``.
- ``/ws/*`` paths are required in the contract but exempt from the dump
  check: FastAPI does not describe WebSocket routes in its generated
  OpenAPI document at all, so a dump can never "contain" them.
- Response codes 401/403/404 are implied by the contract's global auth/jail
  note (see its top-level ``description`` and each tag's) and are skipped
  rather than required verbatim on every operation.
- A dump response schema with no declared ``properties`` at all (FastAPI's
  shape for a route typed ``-> dict[str, Any]`` / ``-> list[dict]``) cannot
  be checked structurally; its required-property gaps are counted as
  *warnings*, not failures, and printed separately so they stay visible.
  The warnings are ratcheted: ``dev/contracts_check_baseline.json`` lists
  every one, a warning not on it fails (the unchecked surface grew), and a
  listed one that no longer occurs fails too until the baseline is rewritten
  with ``--write-baseline`` (so the number only goes down).
- Request bodies: where the server declares the JSON body's properties, every
  property the server requires must be a contract property and every
  property the contract requires must exist on the server (with matching
  type/enum).  An untyped (``dict``) server body is one warning.
- ``PipelineConfig`` is a contract-only documentation union (the real
  discriminant is the ``kind``/path parameter, not a field on a response
  object) with no corresponding named model on the server; it is exempt
  from the named-schema-by-name check.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
CONTRACT_PATH = REPO / "contracts" / "openapi.yaml"
SCHEMA_D_TS = REPO / "desktop" / "src" / "renderer" / "api" / "schema.d.ts"
GENERATED_OPENAPI = REPO / "contracts" / "generated" / "openapi.json"
NODE_MODULES = REPO / "desktop" / "node_modules"
BASELINE_PATH = REPO / "dev" / "contracts_check_baseline.json"

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

# Contract-vs-code differences that are real and open, recorded here so that *new*
# drift still fails red while these stay visible in every run's output.  Remove an
# entry when the underlying issue is fixed -- the gate fails if a listed finding
# stops occurring, so this list cannot rot silently.
#
# Empty since 2026-09-07 (CX8): the twelve findings this list was opened with on the
# same day were all fixed at the cause rather than carried --
#   * Overview*.reason spelled nullability with OpenAPI 3.0's `nullable: true`, which
#     is not a keyword in the 3.1 document it sits in and so said nothing; the server
#     was right to return `str | None`.  Contract now says `type: [string, "null"]`.
#   * Plan*/LockConflict `kind` was a bare `str` on the server, which dumps no enum.
#     Both models now carry `tit.jobs.spec.JobKind`, the contract's enum as a Literal.
#   * POST /api/system/terminate answers 200 with `{pid, terminated}`; the contract
#     claimed a bodiless 204.  The contract was wrong and now describes what ships.
_KNOWN_FINDINGS: frozenset[str] = frozenset()


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


def compare_request_body(
    contract: dict[str, Any],
    c_op: dict[str, Any],
    dump: dict[str, Any],
    d_op: dict[str, Any],
    where: str,
    missing: list[str],
    warnings: list[str],
) -> None:
    """Compare one operation's request body in both directions.

    Every property the server requires must be a contract property (or the desktop,
    written against the contract, never sends it); every property the contract
    declares must exist on the server (or the server silently drops it); and what the
    contract lets a client send must be accepted: its types and enum values are a
    subset of the server's (a server that also takes ``null`` is fine). A JSON body
    the server declares no properties for is untyped: one warning.
    """
    c_content = (c_op.get("requestBody") or {}).get("content", {})
    d_content = (d_op.get("requestBody") or {}).get("content", {})
    if not c_content and not d_content:
        return
    if not d_content:
        missing.append(f"{where}: the contract sends a body the server does not read")
        return
    if not c_content:
        missing.append(
            f"{where}: the server reads a body the contract does not describe"
        )
        return
    for media, c_media in c_content.items():
        if media not in d_content:
            missing.append(f"{where}: media type {media} not accepted by the server")
            continue
        if media != "application/json":
            continue
        c_schema = deref(contract, c_media.get("schema", {}))
        d_schema = deref(dump, d_content[media].get("schema", {}))
        if not _properties(dump, d_schema):
            warnings.append(
                f"{where}: server body is untyped (dict) -- its properties are not checked"
            )
            continue
        c_props = _properties(contract, c_schema)
        d_props = _properties(dump, d_schema)
        for name in d_schema.get("required", []):
            if name not in c_props:
                missing.append(
                    f"{where}: server-required property '{name}' missing from the contract"
                )
        for name, c_prop in c_props.items():
            if name not in d_props:
                missing.append(
                    f"{where}: contract property '{name}' unknown to the server"
                )
                continue
            c_types = _types(contract, c_prop)
            d_types = _types(dump, d_props[name])
            if c_types and d_types and not c_types <= d_types:
                missing.append(
                    f"{where}.{name}: the contract sends {sorted(c_types)}, "
                    f"the server accepts {sorted(d_types)}"
                )
            c_enum = _enum(contract, c_prop)
            d_enum = _enum(dump, d_props[name])
            if c_enum is not None and d_enum is not None:
                refused = [v for v in c_enum if v not in d_enum]
                if refused:
                    missing.append(
                        f"{where}.{name}: the server refuses contract values {refused}"
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
            compare_request_body(
                contract,
                c_op,
                dump,
                d_op,
                f"{method.upper()} {path} requestBody",
                missing,
                warnings,
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
            # Same root cause as finding 3d below: the router returns bare
            # ``dict``/``list``, so FastAPI never registers a named model for it.
            # The contract documents the shape anyway (the UI is written against
            # it); there is simply nothing on the server side to compare it to.
            # Counted and printed as a warning so the unverified surface stays
            # visible, rather than failing a gate it can never pass until those
            # routers grow response models.
            warnings.append(f"schema {name} has no named model on the server")
            continue
        compare_schema(
            contract, c_schema, dump, d_schema, f"schema {name}", missing, warnings
        )
    return missing, warnings


def schema_d_ts_mode(
    *,
    env: Mapping[str, str],
    npx_found: bool,
    node_modules: bool,
    skip_requested: bool,
) -> str:
    """How the ``schema.d.ts`` drift check runs here.

    Returns:
        ``"run"`` when ``openapi-typescript`` is installed; ``"skipped"`` when the
        caller passed ``--no-schema-d-ts`` (another CI step diffs it); ``"local-skip"``
        on a developer tree without ``desktop/node_modules``; ``"cannot"`` when ``CI``
        is set and the tool is missing, which the gate reports as exit 2.
    """
    if skip_requested:
        return "skipped"
    if npx_found and node_modules:
        return "run"
    if env.get("CI", "").strip().lower() in {"1", "true", "yes"}:
        return "cannot"
    return "local-skip"


def check_drift(schema_d_ts: str = "run") -> list[str]:
    """Regenerate every ``contracts/generated/`` output in memory; report what would change.

    Args:
        schema_d_ts: A :func:`schema_d_ts_mode` result; only ``"run"`` regenerates
            ``schema.d.ts``.
    """
    sys.path.insert(0, str(REPO / "dev"))
    import build_contract
    import build_contracts
    import build_schema

    # Same host/container import bootstrap `npm run gen` uses.
    build_contracts._ensure_importable()

    problems: list[str] = []
    if build_schema.main(["--check"]) != 0:
        problems.append(f"{build_schema.OUTPUT_PATH.relative_to(REPO)} is stale")
    if build_contract.main(["--check"]) != 0:
        problems.append(f"{GENERATED_OPENAPI.relative_to(REPO)} is stale")

    if schema_d_ts == "skipped":
        print(
            "contracts_check: schema.d.ts not checked here (--no-schema-d-ts); "
            "the step that passed it must diff it"
        )
    elif schema_d_ts != "run":
        print(
            "contracts_check: skipping schema.d.ts (desktop/node_modules not installed); "
            "`npm run gen` in desktop/ checks it"
        )
    else:
        npx = shutil.which("npx") or "npx"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "schema.d.ts"
            result = subprocess.run(
                [npx, "openapi-typescript", str(GENERATED_OPENAPI), "-o", str(out)],
                cwd=REPO / "desktop",
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                problems.append(
                    f"openapi-typescript failed: {result.stderr.strip()[:400]}"
                )
            elif out.read_text(encoding="utf-8") != SCHEMA_D_TS.read_text(
                encoding="utf-8"
            ):
                problems.append(f"{SCHEMA_D_TS.relative_to(REPO)} is stale")
    return problems


def load_baseline(path: Path) -> list[str]:
    """The recorded warnings.

    Raises:
        ValueError: If the file is missing or is not ``{"warnings": [str, ...]}``.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    warnings = data.get("warnings") if isinstance(data, dict) else None
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings):
        raise ValueError(f'{path} is not {{"warnings": [str, ...]}}')
    return warnings


def write_baseline(path: Path, warnings: list[str]) -> None:
    """Record ``warnings`` (sorted) as the new ceiling."""
    document = {
        "_comment": (
            "Every contracts_check warning (an untyped dict/list response or body, or a "
            "contract schema with no server model). dev/contracts_check.py fails when a "
            "warning appears that is not listed, and when a listed one stops occurring; "
            "rewrite with `python3 dev/contracts_check.py --write-baseline` after "
            "removing one."
        ),
        "warnings": sorted(warnings),
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def ratchet(warnings: list[str], baseline: list[str]) -> list[str]:
    """Every way ``warnings`` differs from ``baseline`` (a multiset comparison).

    A warning not in the baseline means the unchecked surface grew; a baseline entry
    that no longer occurs means it shrank and the baseline must be lowered to match.
    """
    current, recorded = Counter(warnings), Counter(baseline)
    grew = sorted((current - recorded).elements())
    gone = sorted((recorded - current).elements())
    return [f"new warning (not in the baseline): {w}" for w in grew] + [
        f"no longer occurs (lower the baseline): {w}" for w in gone
    ]


def live_openapi() -> dict[str, Any]:
    """This server's own OpenAPI document, built in-process.

    The same object ``tit.server.__main__ --dump-openapi`` writes and
    ``GET /api/openapi.json`` serves, so there is no committed copy to go stale.
    """
    sys.path.insert(0, str(REPO))
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    with tempfile.TemporaryDirectory() as project_dir:
        return create_app(
            ServerSettings(project_dir=project_dir, token="contracts-check")
        ).openapi()


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="contracts_check",
        description="Check contracts/openapi.yaml against the live app and contracts/generated/.",
    )
    parser.add_argument(
        "--no-schema-d-ts",
        action="store_true",
        help="do not regenerate schema.d.ts here (another CI step diffs it)",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help=f"record the current warnings in {BASELINE_PATH.name} instead of comparing",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = _parse(argv[1:])
    except SystemExit as exc:  # argparse: --help is 0, a usage error is 2
        return 0 if exc.code == 0 else 2

    mode = schema_d_ts_mode(
        env=os.environ,
        npx_found=shutil.which("npx") is not None,
        node_modules=NODE_MODULES.is_dir(),
        skip_requested=args.no_schema_d_ts,
    )
    if mode == "cannot":
        print(
            f"contracts_check: cannot check {SCHEMA_D_TS.relative_to(REPO)}: CI is set and "
            "desktop/node_modules is not installed. Run `npm ci` in desktop/ first, or pass "
            "--no-schema-d-ts in a job where another step diffs it.",
            file=sys.stderr,
        )
        return 2
    baseline: list[str] | None = None
    if not args.write_baseline:
        try:
            baseline = load_baseline(BASELINE_PATH)
        except ValueError as exc:
            print(f"contracts_check: {exc}", file=sys.stderr)
            return 2

    drift = check_drift(mode)
    if drift:
        print(f"contracts_check: {len(drift)} generated file(s) out of date:")
        for line in drift:
            print(f"  - {line}")
        print("\nRun `npm run gen` (in desktop/) and commit the result.")
        return 1
    print("contracts_check: contracts/generated/ is up to date")

    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    dump = live_openapi()
    missing, warnings = check(contract, dump)

    def _key(line: str) -> str:
        """The ``_KNOWN_FINDINGS`` entry a finding matches: full line, else its subject."""
        return line if line in _KNOWN_FINDINGS else line.split(":")[0]

    known = [m for m in missing if _key(m) in _KNOWN_FINDINGS]
    missing = [m for m in missing if _key(m) not in _KNOWN_FINDINGS]
    stale_known = _KNOWN_FINDINGS - {_key(m) for m in known}
    n_paths = sum(
        1 for item in contract["paths"].values() for m in METHODS if m in item
    )
    n_schemas = len(contract.get("components", {}).get("schemas", {}))
    if warnings:
        print(f"contracts_check: {len(warnings)} warning(s) (ratcheted, see below):")
        for line in warnings:
            print(f"  - {line}")
    if known:
        print(f"contracts_check: {len(known)} known open finding(s) (_KNOWN_FINDINGS):")
        for line in known:
            print(f"  - {line}")
    if stale_known:
        print(
            f"contracts_check: {len(stale_known)} _KNOWN_FINDINGS entr(y/ies) no longer "
            "occur -- delete them from dev/contracts_check.py:"
        )
        for line in sorted(stale_known):
            print(f"  - {line}")
        return 1
    if missing:
        print(f"contracts_check: {len(missing)} problem(s):")
        for line in missing:
            print(f"  - {line}")
        return 1
    if args.write_baseline:
        write_baseline(BASELINE_PATH, warnings)
        print(
            f"contracts_check: wrote {len(warnings)} warning(s) to "
            f"{BASELINE_PATH.name}"
        )
        return 0
    moved = ratchet(warnings, baseline or [])
    if moved:
        print(
            f"contracts_check: {len(warnings)} warning(s), baseline "
            f"{len(baseline or [])} ({BASELINE_PATH.name}):"
        )
        for line in moved:
            print(f"  - {line}")
        print(
            "\nA new warning means a route or schema the gate cannot check: give it a "
            "response/body model. A gone one: run `python3 dev/contracts_check.py "
            "--write-baseline` and commit the lower baseline."
        )
        return 1
    print(
        f"contracts_check: OK -- {n_paths} operation(s) and {n_schemas} schema(s) "
        f"from {CONTRACT_PATH.name} are served by the live app"
        + (
            f" ({len(warnings)} warning(s) above, equal to the baseline)"
            if warnings
            else ""
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
