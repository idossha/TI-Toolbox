"""The error types the job manager writes are the ones the desktop app labels, and no others.

What it pins: a failed job's ``error.type`` is shown through
``desktop/src/renderer/app/jobs-rail/format.ts::ERROR_LABEL``. Before 2026-10-22 that table
labelled five types the server never emits (``preflight``, ``lock_wait``, ``budget_wait``,
``oom_suspected``, ``docker_unavailable``) plus ``cancelled`` (a cancelled job carries no error),
while the two it does emit (``forced``, ``spawn_error``) fell through to a title-cased guess.

Where the expected values come from: the server side is every ``JobError(type="...")`` literal
in ``tit/jobs/*.py``, collected with :mod:`ast` (so a multi-line call counts); the desktop side
is the object literal in ``format.ts``, read as text. Neither side is retyped here. ``UI_ONLY``
is the explicit list of labels the desktop may keep without a server emitter (none today). Also
checks ``JOB_KINDS``/``JOB_STATES`` against the ``JobKind``/``JobState`` enums of
``contracts/openapi.yaml``.

Reproduce: ``.venv/bin/python -m pytest tests/test_job_error_taxonomy_contract.py -q``.
Deliberately elsewhere: the desktop's kind/state/panel lists
(``desktop/tests/unit/job-vocabulary-contract.test.ts``).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import yaml

from tit.jobs import spec

REPO = Path(__file__).resolve().parents[1]
FORMAT_TS = REPO / "desktop/src/renderer/app/jobs-rail/format.ts"

#: Labels the desktop may keep although no server code emits the type. Empty: every label must
#: have an emitter, so a new UI-only label is a decision someone writes down here.
UI_ONLY: frozenset[str] = frozenset()


def job_error_types(source: str) -> tuple[set[str], int]:
    """Every literal ``type`` of a ``JobError(...)`` call, and how many calls had no literal."""
    found: set[str] = set()
    unreadable = 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "JobError":
            continue
        value = next((k.value for k in node.keywords if k.arg == "type"), None)
        if value is None and node.args:
            value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            found.add(value.value)
        else:
            unreadable += 1
    return found, unreadable


def error_label_keys(source: str) -> set[str]:
    """The keys of ``const ERROR_LABEL ... = { ... };`` in ``format.ts``."""
    match = re.search(r"const ERROR_LABEL[^=]*=\s*\{(.*?)\n\};", source, re.S)
    assert match, "ERROR_LABEL object literal not found in format.ts"
    return set(re.findall(r"^\s+([A-Za-z_]+):", match.group(1), re.M))


def taxonomy_violations(server: set[str], labels: set[str]) -> list[str]:
    """Human-readable disagreements; empty when the two sides agree."""
    out = [f"server emits {t!r} with no desktop label" for t in sorted(server - labels)]
    out += [
        f"desktop labels {t!r}, which no server code emits"
        for t in sorted(labels - server - UI_ONLY)
    ]
    return out


def _server_types() -> set[str]:
    types: set[str] = set()
    for path in sorted((REPO / "tit" / "jobs").glob("*.py")):
        found, unreadable = job_error_types(path.read_text())
        assert unreadable == 0, f"{path.name}: a JobError type is not a literal"
        types |= found
    return types


def test_every_server_error_type_is_labelled_and_every_label_is_emitted() -> None:
    server = _server_types()
    labels = error_label_keys(FORMAT_TS.read_text())
    assert {"runner_failed", "lost"} <= server  # the collector found the common ones
    assert taxonomy_violations(server, labels) == []


def test_the_collector_sees_a_planted_multiline_job_error() -> None:
    planted = 'x = JobError(\n    type="planted_type",\n    message="m",\n)\n'
    found, unreadable = job_error_types(planted)
    assert found == {"planted_type"} and unreadable == 0
    _, unreadable = job_error_types("JobError(type=kind, message='m')")
    assert unreadable == 1


def test_a_planted_label_or_emitter_is_reported() -> None:
    server = _server_types()
    text = FORMAT_TS.read_text()
    planted = text.replace(
        "const ERROR_LABEL: Record<string, string> = {",
        'const ERROR_LABEL: Record<string, string> = {\n  planted_label: "Planted",',
    )
    assert planted != text
    labels = error_label_keys(planted)
    assert taxonomy_violations(server, labels) == [
        "desktop labels 'planted_label', which no server code emits"
    ]
    assert taxonomy_violations(
        server | {"planted_emit"}, labels - {"planted_label"}
    ) == ["server emits 'planted_emit' with no desktop label"]


def test_job_kinds_and_states_match_the_contract_enums() -> None:
    schemas = yaml.safe_load((REPO / "contracts/openapi.yaml").read_text())[
        "components"
    ]["schemas"]
    assert sorted(spec.JOB_KINDS) == sorted(schemas["JobKind"]["enum"])
    assert sorted(spec.JOB_STATES) == sorted(schemas["JobState"]["enum"])
    assert spec.TERMINAL_STATES < set(spec.JOB_STATES)
