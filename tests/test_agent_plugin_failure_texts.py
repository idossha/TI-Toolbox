"""The failure tables and force/cancel claims an agent reads are the job manager's, 2026-10-22.

What this pins, in ``agent-plugin/skills/*/SKILL.md`` and ``agent-plugin/README.md``:

* the ti-toolbox skill's ``| type | label |`` table: exactly the ``error.type`` values the job
  manager writes, each with the label the app shows;
* the troubleshoot-project skill's ``| error.type | Shown as | What it means |`` table: the same
  types, the same labels, and a meaning for each;
* every "force ... lands (it) in (state) `X` (with `forced`)" claim: a running (or lost) job
  forced lands in the state ``JobManager.force`` gives it, a queued one in the other, and the
  error type is the one ``force`` writes;
* "a job you cancel carries no ``error.type``": every ``cancelled`` the job manager writes for a
  cancel has ``error=None``.

Where the expected values come from: the ``JobError(type=...)`` literals under ``tit/jobs``,
``ERROR_LABEL`` in ``desktop/src/renderer/app/jobs-rail/format.ts``, and the ``state = ...``
expression and ``_finalize_locked`` calls of ``tit/jobs/manager.py``, all read off disk at test
time; nothing is retyped from the skills.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_failure_texts.py -q
Deliberately elsewhere: the count words ("six ``error.type`` values") and the restart rule
(tests/test_agent_plugin_facts.py), the quick facts ``failure_taxonomy``
(tests/test_agent_plugin_constants.py), the job manager's behaviour itself
(tests/test_jobs_manager.py).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "agent-plugin"
SKILLS = PLUGIN / "skills"
MANAGER = REPO / "tit" / "jobs" / "manager.py"


def _emitted() -> set[str]:
    """Every literal ``JobError(type=...)`` under tit/jobs."""
    found = set()
    for path in sorted((REPO / "tit" / "jobs").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            func = getattr(node, "func", None)
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if isinstance(node, ast.Call) and name == "JobError":
                [value] = [k.value for k in node.keywords if k.arg == "type"]
                found.add(value.value)
    assert {"runner_failed", "lost"} <= found  # the collector found the common ones
    return found


def _labels() -> dict[str, str]:
    fmt = (REPO / "desktop/src/renderer/app/jobs-rail/format.ts").read_text()
    table = re.search(r"const ERROR_LABEL[^{]*\{(.*?)\};", fmt, re.S).group(1)
    labels = dict(re.findall(r'(\w+): "([^"]+)"', table))
    assert labels  # the parse found the table
    return labels


def _table_after(text: str, lead: str) -> list[list[str]]:
    """The body rows of the markdown table that follows the line containing *lead*."""
    lines = text.splitlines()
    [start] = [i for i, line in enumerate(lines) if lead in line]
    rows = []
    for line in lines[start + 1 :]:
        if not line.strip():
            if rows:
                break
            continue
        if not line.startswith("|"):
            break
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    # rows[0] is the header, rows[1] the |---| separator.
    assert len(rows) > 2 and set(rows[1][0]) <= set("-: "), rows[:2]
    return rows[2:]


def _bare(cell: str) -> str:
    """A cell without its bold and code marks: **`lost`** -> lost."""
    return cell.replace("*", "").strip().strip("`")


def test_the_ti_toolbox_table_is_the_job_managers_types_with_the_apps_labels():
    text = (SKILLS / "ti-toolbox" / "SKILL.md").read_text()
    rows = _table_after(
        text, "Failure `error.type` values and the wording the UI shows"
    )
    assert all(len(r) == 2 for r in rows), rows
    table = {_bare(t): _bare(label) for t, label in rows}
    assert len(table) == len(rows)  # no type listed twice
    assert set(table) == _emitted()
    assert table == _labels()


def test_the_troubleshoot_table_is_the_job_managers_types_with_the_apps_labels():
    text = (SKILLS / "troubleshoot-project" / "SKILL.md").read_text()
    rows = _table_after(text, "Map the `error.type` to what to tell the user")
    assert all(len(r) == 3 for r in rows), rows
    types = [_bare(r[0]) for r in rows]
    assert len(types) == len(set(types))
    assert set(types) == _emitted()
    assert {_bare(t): _bare(shown) for t, shown, _ in rows} == _labels()
    for t, _, meaning in rows:
        assert len(meaning.split()) >= 3, f"{t}: no meaning given"


def _force_states() -> tuple[dict[str, str], str]:
    """``JobManager.force``: the state a forced job lands in, by the state it was in, and the
    error type it writes."""
    tree = ast.parse(MANAGER.read_text())
    [force] = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "force"
    ]
    [assign] = [
        n
        for n in ast.walk(force)
        if isinstance(n, ast.Assign)
        and [getattr(t, "id", None) for t in n.targets] == ["state"]
    ]
    choice = assign.value
    assert isinstance(choice, ast.IfExp), ast.dump(choice)
    test = choice.test
    assert isinstance(test, ast.Compare) and test.comparators[0].value == "queued"
    if isinstance(test.ops[0], ast.NotEq):
        landed = {"running": choice.body.value, "queued": choice.orelse.value}
    else:
        assert isinstance(test.ops[0], ast.Eq)
        landed = {"running": choice.orelse.value, "queued": choice.body.value}
    [etype] = [
        k.value.value
        for n in ast.walk(force)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "JobError"
        for k in n.keywords
        if k.arg == "type"
    ]
    return landed, etype


@pytest.fixture(scope="module")
def texts() -> dict[str, str]:
    docs = sorted(SKILLS.glob("*/SKILL.md")) + [PLUGIN / "README.md"]
    return {str(p.relative_to(REPO)): p.read_text() for p in docs}


_LANDS = re.compile(
    r"lands\s+(?:it\s+)?in\s+(?:state\s+)?`(\w+)`"
    r"(?:\s+with\s+(?:`error\.type`\s+)?`(\w+)`)?"
)
_IF_QUEUED = re.compile(r"`(\w+)`\s+if\s+it\s+was\s+still\s+queued")


def test_every_force_claim_is_the_job_managers(texts):
    landed, etype = _force_states()
    assert landed["running"] != landed["queued"]  # the parse read both branches
    claims = set()
    for name, text in texts.items():
        for sentence in re.split(r"(?<=[.;])\s+|\n\s*\n", text):
            for m in _LANDS.finditer(sentence):
                # "a queued job you force-stop lands in ..." is the queued case; any other
                # "lands in" is the job that was running (or already lost).
                when = (
                    "queued"
                    if re.search(r"\bqueued\b", sentence[: m.start()])
                    else "running"
                )
                claims.add((name, when))
                assert m.group(1) == landed[when], f"{name}: {m.group(0)!r} ({when})"
                if m.group(2):
                    assert m.group(2) == etype, f"{name}: {m.group(0)!r}"
            for m in _IF_QUEUED.finditer(sentence):
                claims.add((name, "queued"))
                assert m.group(1) == landed["queued"], f"{name}: {m.group(0)!r}"
    skill = "agent-plugin/skills/{}/SKILL.md".format
    assert {
        (skill("ti-toolbox"), "running"),
        (skill("troubleshoot-project"), "running"),
        (skill("troubleshoot-project"), "queued"),
        (skill("ti-codebase"), "running"),
        (skill("ti-codebase"), "queued"),
    } <= claims


def test_a_cancelled_job_carries_no_error_type(texts):
    """Every ``_finalize_locked(..., state="cancelled", ...)`` in the job manager (a user's
    cancel, and a cancelled runner's exit) passes ``error=None``; only ``force`` on a queued
    job writes ``cancelled`` with an error, and that one is the force claim above."""
    tree = ast.parse(MANAGER.read_text())
    cancelled = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", None) == "_finalize_locked"
        ):
            kw = {k.arg: k.value for k in node.keywords}
            state = kw.get("state")
            if isinstance(state, ast.Constant) and state.value == "cancelled":
                cancelled.append(kw.get("error"))
    assert len(cancelled) >= 2  # the cancel and the runner-exit paths
    assert all(isinstance(e, ast.Constant) and e.value is None for e in cancelled)
    said = texts["agent-plugin/skills/troubleshoot-project/SKILL.md"]
    assert re.search(r"A job you cancel carries no\s+`error\.type`", said)
