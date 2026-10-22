"""Self-tests for ``dev/contracts_check.py``: request bodies, the warning ratchet, honest skips.

What this pins
--------------
* Request bodies are compared in both directions: a property the server requires
  but the contract does not declare, a contract property the server does not
  know, a contract type or enum value the server refuses, a body on one side
  only, and a media type the server does not accept are each a finding; a server
  that accepts *more* (``string | null`` for the contract's ``string``) is not.
  An untyped JSON body is one warning, not a finding.
* The warnings are ratcheted against ``dev/contracts_check_baseline.json``: one
  warning more than the baseline exits 1, one fewer exits 1 (lower the baseline),
  equal exits 0, an unreadable baseline exits 2.
* ``CI`` set without ``desktop/node_modules`` exits 2 before checking anything,
  unless the job says ``--no-schema-d-ts``; a developer tree only prints a skip.
* The committed baseline equals the live app's warnings today.

Every expected finding below is derived by hand from the fixture dicts next to
it (the message wording is the guard's, the *which property / which path* is
the fixture's). Reproduce: ``.venv/bin/python -m pytest tests/test_contracts_check_unit.py -q``.
``test_server_skeleton.py`` keeps the response-side type/enum self-test.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "contracts_check_selftest", REPO / "dev" / "contracts_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def cc():
    return _load()


def _op_with_body(schema: dict | None, media: str = "application/json") -> dict:
    op: dict = {"responses": {"204": {"description": "done"}}}
    if schema is not None:
        op["requestBody"] = {"content": {media: {"schema": schema}}}
    return op


def _doc(op: dict, schemas: dict | None = None) -> dict:
    return {"paths": {"/x": {"post": op}}, "components": {"schemas": schemas or {}}}


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required}


STR = {"type": "string"}


# -- request bodies ---------------------------------------------------------------


def test_matching_bodies_and_a_server_that_also_accepts_null_are_clean(cc) -> None:
    contract = _doc(_op_with_body(_obj({"a": STR, "b": STR}, ["a"])))
    dump = _doc(
        _op_with_body(
            _obj(
                {"a": STR, "b": {"anyOf": [STR, {"type": "null"}]}},
                ["a"],
            )
        )
    )
    missing, warnings = cc.check(contract, dump)
    assert missing == [] and warnings == []


def test_a_server_required_property_missing_from_the_contract_is_a_finding(
    cc,
) -> None:
    contract = _doc(_op_with_body(_obj({"a": STR}, ["a"])))
    dump = _doc(_op_with_body(_obj({"a": STR, "secret": STR}, ["a", "secret"])))
    missing, _ = cc.check(contract, dump)
    assert missing == [
        "POST /x requestBody: server-required property 'secret' missing from the contract"
    ]


def test_a_contract_property_the_server_does_not_know_is_a_finding(cc) -> None:
    contract = _doc(_op_with_body(_obj({"a": STR, "space": STR}, ["a"])))
    dump = _doc(_op_with_body(_obj({"a": STR}, ["a"])))
    missing, _ = cc.check(contract, dump)
    assert missing == [
        "POST /x requestBody: contract property 'space' unknown to the server"
    ]


def test_a_contract_required_property_the_server_does_not_know_is_a_finding(
    cc,
) -> None:
    contract = _doc(_op_with_body(_obj({"a": STR, "kind": STR}, ["a", "kind"])))
    dump = _doc(_op_with_body(_obj({"a": STR}, ["a"])))
    missing, _ = cc.check(contract, dump)
    assert (
        "POST /x requestBody: contract property 'kind' unknown to the server" in missing
    )


def test_a_type_or_enum_the_server_refuses_is_a_finding(cc) -> None:
    contract = _doc(
        _op_with_body(
            _obj(
                {
                    "n": {"type": "number"},
                    "m": {"type": "string", "enum": ["U", "M", "Q"]},
                },
                [],
            )
        )
    )
    dump = _doc(
        _op_with_body(
            _obj(
                {"n": {"type": "integer"}, "m": {"type": "string", "enum": ["M", "U"]}},
                [],
            )
        )
    )
    missing, _ = cc.check(contract, dump)
    assert sorted(missing) == [
        "POST /x requestBody.m: the server refuses contract values ['Q']",
        "POST /x requestBody.n: the contract sends ['number'], the server accepts ['integer']",
    ]


def test_a_body_on_one_side_only_is_a_finding(cc) -> None:
    body = _obj({"a": STR}, ["a"])
    missing, _ = cc.check(_doc(_op_with_body(None)), _doc(_op_with_body(body)))
    assert missing == [
        "POST /x requestBody: the server reads a body the contract does not describe"
    ]
    missing, _ = cc.check(_doc(_op_with_body(body)), _doc(_op_with_body(None)))
    assert missing == [
        "POST /x requestBody: the contract sends a body the server does not read"
    ]


def test_a_media_type_the_server_does_not_accept_is_a_finding(cc) -> None:
    contract = _doc(_op_with_body({"type": "string"}, media="text/csv"))
    same = _doc(_op_with_body({"type": "string"}, media="text/csv"))
    other = _doc(_op_with_body({"type": "object"}, media="application/json"))
    assert cc.check(contract, same) == ([], [])
    missing, _ = cc.check(contract, other)
    assert missing == [
        "POST /x requestBody: media type text/csv not accepted by the server"
    ]


def test_an_untyped_server_body_is_one_warning(cc) -> None:
    contract = _doc(_op_with_body(_obj({"a": STR}, ["a"])))
    dump = _doc(_op_with_body({"type": "object", "additionalProperties": True}))
    missing, warnings = cc.check(contract, dump)
    assert missing == []
    assert warnings == [
        "POST /x requestBody: server body is untyped (dict) -- its properties are not checked"
    ]


def test_body_schemas_are_followed_through_refs(cc) -> None:
    contract = _doc(
        _op_with_body({"$ref": "#/components/schemas/Req"}),
        {"Req": _obj({"a": STR}, ["a"])},
    )
    dump = _doc(
        _op_with_body({"$ref": "#/components/schemas/Req"}),
        {"Req": _obj({"a": STR, "b": STR}, ["a", "b"])},
    )
    missing, _ = cc.check(contract, dump)
    assert (
        "POST /x requestBody: server-required property 'b' missing from the contract"
        in missing
    )


# -- the ratchet and the exit codes ----------------------------------------------

# A contract whose check against UNTYPED_DUMP yields exactly two warnings, by hand:
# GET /y's 200 requires `z` but the dump response declares no properties, and
# component `Z` has no server model.
RATCHET_CONTRACT = {
    "paths": {
        "/y": {
            "get": {
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {"schema": _obj({"z": STR}, ["z"])}
                        },
                    }
                }
            }
        }
    },
    "components": {"schemas": {"Z": _obj({"z": STR}, ["z"])}},
}
UNTYPED_DUMP = {
    "paths": {
        "/y": {
            "get": {
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                }
            }
        }
    },
    "components": {"schemas": {}},
}
TWO_WARNINGS = [
    "GET /y 200: required property 'z' missing (dump response has no declared schema "
    "-- dict/list response)",
    "schema Z has no named model on the server",
]


@pytest.fixture()
def gate(cc, tmp_path, monkeypatch):
    """The module with its expensive halves replaced by the hand-built documents."""
    contract_path = tmp_path / "openapi.yaml"
    contract_path.write_text(json.dumps(RATCHET_CONTRACT))  # JSON is YAML
    node_modules = tmp_path / "node_modules"
    node_modules.mkdir()
    monkeypatch.setattr(cc, "CONTRACT_PATH", contract_path)
    monkeypatch.setattr(cc, "BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(cc, "NODE_MODULES", node_modules)
    monkeypatch.setattr(cc, "check_drift", lambda mode="run": [])
    monkeypatch.setattr(cc, "live_openapi", lambda: UNTYPED_DUMP)
    monkeypatch.delenv("CI", raising=False)
    return cc


def _baseline(gate, warnings: list[str]) -> None:
    gate.BASELINE_PATH.write_text(json.dumps({"warnings": warnings}))


def test_the_hand_built_documents_give_the_two_hand_derived_warnings(gate) -> None:
    missing, warnings = gate.check(RATCHET_CONTRACT, UNTYPED_DUMP)
    assert missing == []
    assert sorted(warnings) == sorted(TWO_WARNINGS)


def test_warnings_equal_to_the_baseline_pass(gate) -> None:
    _baseline(gate, TWO_WARNINGS)
    assert gate.main(["contracts_check"]) == 0


def test_a_warning_above_the_baseline_fails(gate, capsys) -> None:
    _baseline(gate, TWO_WARNINGS[:1])
    assert gate.main(["contracts_check"]) == 1
    out = capsys.readouterr().out
    assert f"new warning (not in the baseline): {TWO_WARNINGS[1]}" in out


def test_a_warning_below_the_baseline_fails_until_the_baseline_is_lowered(
    gate, capsys
) -> None:
    gone = "GET /old 200: required property 'q' missing (dump response has no declared schema -- dict/list response)"
    _baseline(gate, TWO_WARNINGS + [gone])
    assert gate.main(["contracts_check"]) == 1
    assert f"no longer occurs (lower the baseline): {gone}" in capsys.readouterr().out

    assert gate.main(["contracts_check", "--write-baseline"]) == 0
    written = json.loads(gate.BASELINE_PATH.read_text())["warnings"]
    assert written == sorted(TWO_WARNINGS)
    assert gate.main(["contracts_check"]) == 0


def test_a_swapped_warning_with_the_same_count_still_fails(gate) -> None:
    other = "schema Q has no named model on the server"
    _baseline(gate, [TWO_WARNINGS[0], other])
    assert gate.main(["contracts_check"]) == 1


def test_a_second_copy_of_a_listed_warning_is_new(gate, monkeypatch, capsys) -> None:
    """The baseline is a multiset: the same line twice is two unchecked surfaces.

    Two operations can yield the identical line (one schema reached twice, say);
    a set comparison would let the second one in unnoticed.
    """
    twice = TWO_WARNINGS + [TWO_WARNINGS[1]]
    monkeypatch.setattr(gate, "check", lambda contract, dump: ([], twice))
    _baseline(gate, TWO_WARNINGS)
    assert gate.main(["contracts_check"]) == 1
    out = capsys.readouterr().out
    assert out.count("new warning (not in the baseline): ") == 1
    assert f"new warning (not in the baseline): {TWO_WARNINGS[1]}" in out


def test_a_warning_listed_twice_that_now_occurs_once_must_be_lowered(gate) -> None:
    _baseline(gate, TWO_WARNINGS + [TWO_WARNINGS[0]])
    assert gate.ratchet(TWO_WARNINGS, TWO_WARNINGS + [TWO_WARNINGS[0]]) == [
        f"no longer occurs (lower the baseline): {TWO_WARNINGS[0]}"
    ]
    assert gate.main(["contracts_check"]) == 1


@pytest.mark.parametrize("content", [None, "not json", json.dumps({"warnings": "x"})])
def test_an_unreadable_baseline_is_could_not_check(gate, content) -> None:
    if content is not None:
        gate.BASELINE_PATH.write_text(content)
    assert gate.main(["contracts_check"]) == 2


def test_an_unknown_argument_is_could_not_check(gate) -> None:
    assert gate.main(["contracts_check", "--bogus"]) == 2


def test_ci_without_node_modules_exits_2_before_checking_anything(
    gate, monkeypatch, tmp_path, capsys
) -> None:
    _baseline(gate, TWO_WARNINGS)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(gate, "NODE_MODULES", tmp_path / "absent")

    def boom(*_args, **_kwargs):
        raise AssertionError("must not run after deciding it cannot check")

    monkeypatch.setattr(gate, "check_drift", boom)
    assert gate.main(["contracts_check"]) == 2
    assert (
        "cannot check desktop/src/renderer/api/schema.d.ts" in capsys.readouterr().err
    )


def test_ci_with_an_explicit_no_schema_d_ts_runs_the_rest(
    gate, monkeypatch, tmp_path
) -> None:
    _baseline(gate, TWO_WARNINGS)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(gate, "NODE_MODULES", tmp_path / "absent")
    modes: list[str] = []
    monkeypatch.setattr(
        gate, "check_drift", lambda mode="run": modes.append(mode) or []
    )
    assert gate.main(["contracts_check", "--no-schema-d-ts"]) == 0
    assert modes == ["skipped"]


@pytest.mark.parametrize(
    ("ci", "npx", "node_modules", "skip", "expected"),
    [
        (None, True, True, False, "run"),
        ("true", True, True, False, "run"),
        ("true", True, False, False, "cannot"),
        ("true", False, True, False, "cannot"),
        ("1", False, False, False, "cannot"),
        (None, True, False, False, "local-skip"),
        ("", False, False, False, "local-skip"),
        ("true", False, False, True, "skipped"),
        (None, True, True, True, "skipped"),
    ],
)
def test_schema_d_ts_mode(cc, ci, npx, node_modules, skip, expected) -> None:
    env = {} if ci is None else {"CI": ci}
    mode = cc.schema_d_ts_mode(
        env=env, npx_found=npx, node_modules=node_modules, skip_requested=skip
    )
    assert mode == expected


# -- the repository passes its own guard -----------------------------------------


def test_the_committed_baseline_is_the_live_apps_warnings(cc, tmp_path) -> None:
    yaml = pytest.importorskip("yaml")
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    contract = yaml.safe_load(cc.CONTRACT_PATH.read_text(encoding="utf-8"))
    dump = create_app(ServerSettings(project_dir=tmp_path, token="selftest")).openapi()
    missing, warnings = cc.check(contract, dump)
    assert missing == []
    baseline = cc.load_baseline(cc.BASELINE_PATH)
    assert len(baseline) > 100, "the baseline lost its entries"
    assert cc.ratchet(warnings, baseline) == []
    # The request-body direction is in the baseline too, not silently absent.
    assert any("requestBody: server body is untyped" in w for w in baseline)
