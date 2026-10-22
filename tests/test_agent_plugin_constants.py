"""The agent plugin's copied constants equal the ``tit`` values they copy, 2026-10-22.

What this pins: ``agent-plugin/mcp/jobs_server.py`` and ``server.py`` run on the user's host
with no dependencies, so they *copy* job kinds, states, the subject-id rule, container labels
and proposal states from ``tit`` instead of importing them. Each copy is compared with its
source here:

| Plugin | Source of truth |
|---|---|
| ``GROUP_KINDS`` | ``tit.jobs.plans.GROUP_KINDS`` |
| ``FLEX_KINDS`` | ``tit.jobs.kinds.FLEX_KINDS`` and ``tit.server.proposals.FLEX_KINDS`` |
| ``TERMINAL_STATES`` | ``tit.jobs.spec.TERMINAL_STATES`` |
| ``SUBJECT_ID_RE`` | ``tit.paths.SUBJECT_ID_RE`` |
| ``STACK_ID``, ``LABEL_*``, ``DEFAULT_PORT`` | ``tit.launch`` |
| ``PROPOSAL_DONE`` / ``STEP_DONE`` | the states ``tit.server.proposals.view`` / ``_step_state`` can never leave |
| the ``kind`` description | ``tit.jobs.spec.JOB_KINDS`` |
| quick facts ``job_kinds`` / ``job_states`` | ``tit.jobs.spec.JOB_KINDS`` / ``JOB_STATES`` |
| quick facts ``failure_taxonomy`` | the ``JobError(type=...)`` literals under ``tit/jobs`` and the labels in ``desktop/src/renderer/app/jobs-rail/format.ts`` |

Where the expected values come from: the ``tit`` modules, the frozen contract and the desktop
label table, read at test time. "Final" proposal/step states are computed by driving the
server's own derivation over every input and every later transition (a pending decision is
decided, a live job finishes, a waiting step gets a job): a state is final when no transition
changes it.

Reproduce: .venv/bin/python -m pytest tests/test_agent_plugin_constants.py -q
Deliberately elsewhere: the prose facts (tests/test_agent_plugin_facts.py).
"""

from __future__ import annotations

import ast
import importlib.util
import itertools
import json
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "agent-plugin" / "mcp"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"ti_plugin_{name}", MCP / f"{name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def js():
    return _load("jobs_server")


@pytest.fixture(scope="module")
def facts():
    srv = _load("server")
    resp = srv.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_quick_facts", "arguments": {}},
        }
    )
    return json.loads(resp["result"]["content"][0]["text"])


def test_kinds_states_and_subject_rule_match_tit(js):
    from tit.jobs import kinds, plans, spec
    from tit.paths import SUBJECT_ID_RE
    from tit.server import proposals

    assert js.GROUP_KINDS == plans.GROUP_KINDS
    assert js.FLEX_KINDS == kinds.FLEX_KINDS == proposals.FLEX_KINDS
    assert set(js.TERMINAL_STATES) == spec.TERMINAL_STATES
    assert len(js.TERMINAL_STATES) == len(spec.TERMINAL_STATES)
    assert js.SUBJECT_ID_RE.pattern == SUBJECT_ID_RE.pattern
    assert js.CREATED_BY in spec.CREATED_BY_VALUES


def test_container_labels_match_the_launcher(js):
    from tit import launch

    assert js.STACK_ID == launch.STACK_ID
    assert js.LABEL_STACK == launch.LABEL_STACK
    assert js.LABEL_SERVICE == launch.LABEL_SERVICE
    assert js.LABEL_HOST_DIR == launch.LABEL_HOST_DIR
    assert js.DEFAULT_PORT == str(launch.DEFAULT_PORT)


def test_the_kind_description_names_only_real_kinds(js):
    from tit.jobs.spec import JOB_KINDS

    named = [k.strip() for k in js._KIND["description"].split(",")]
    named = [k for k in named if k and k != "..."]
    assert len(named) >= 5
    assert set(named) <= set(JOB_KINDS), set(named) - set(JOB_KINDS)


# ---------------------------------------------------------------------------------------------
# proposals: which states watch_proposal may treat as "nothing else happens"
# ---------------------------------------------------------------------------------------------


class _Manager:
    def __init__(self, states: dict[str, str | None]):
        self.states = states

    def get(self, job_id: str):
        state = self.states[job_id]
        return None if state is None else {"state": state}


def _step(error=None, skipped=None, job_states=()):
    ids = [f"j{i}" for i in range(len(job_states))]
    return {
        "id": "s",
        "config": {},
        "subject_ids": ["101"],
        "overwrite": False,
        "after": [],
        "error": error,
        "skipped": skipped,
        "job_ids": ids,
    }, dict(zip(ids, job_states))


def _inputs():
    """(decision, error, skipped, job states) over every combination that matters."""
    from tit.jobs.spec import JOB_STATES

    job_lists = (
        [()]
        + [(s,) for s in JOB_STATES]
        + list(itertools.product(JOB_STATES, repeat=2))
    )
    for decision in ("pending", "approved", "rejected"):
        for error, skipped in ((None, None), ("boom", None), (None, "dep failed")):
            for jobs in job_lists:
                yield decision, error, skipped, jobs


def _successors(decision, error, skipped, jobs):
    from tit.jobs.spec import TERMINAL_STATES

    if decision == "pending":
        yield "approved", error, skipped, jobs
        yield "rejected", error, skipped, jobs
    if not jobs and not error and not skipped:
        yield decision, error, skipped, ("queued",)  # the step's job is submitted
    for i, state in enumerate(jobs):
        if state not in TERMINAL_STATES:
            for end in sorted(TERMINAL_STATES):
                yield decision, error, skipped, jobs[:i] + (end,) + jobs[i + 1 :]


def _derive(decision, error, skipped, jobs) -> tuple[str, str]:
    """(step state, proposal status) as the server derives them."""
    from tit.server import proposals

    step, states = _step(error, skipped, jobs)
    record = {
        "id": "p",
        "decision": {"state": decision},
        "steps": [step],
        "proposed_steps": [dict(step)],
    }
    out = proposals.view(record, _Manager(states))
    return out["steps"][0]["state"], out["status"]


def _final_states() -> tuple[set[str], set[str]]:
    seen_step, seen_status, moving_step, moving_status = set(), set(), set(), set()
    for case in _inputs():
        step, status = _derive(*case)
        seen_step.add(step)
        seen_status.add(status)
        for nxt in _successors(*case):
            nstep, nstatus = _derive(*nxt)
            if nstep != step:
                moving_step.add(step)
            if nstatus != status:
                moving_status.add(status)
    return seen_step - moving_step, seen_status - moving_status


def test_watch_proposal_stops_exactly_on_final_states(js):
    final_steps, final_statuses = _final_states()
    # The derivation produced the contract's states, so the search covered them.
    contract = yaml.safe_load((REPO / "contracts/openapi.yaml").read_text())
    schemas = contract["components"]["schemas"]
    step_enum = set(schemas["ProposalStep"]["properties"]["state"]["enum"])
    assert final_steps < step_enum and len(final_steps) >= 3
    assert set(js.STEP_DONE) == final_steps
    assert set(js.PROPOSAL_DONE) == final_statuses
    assert len(js.STEP_DONE) == len(final_steps)


# ---------------------------------------------------------------------------------------------
# get_quick_facts
# ---------------------------------------------------------------------------------------------


def test_quick_facts_kinds_and_states_are_the_job_models(facts):
    from tit.jobs.spec import JOB_KINDS, JOB_STATES

    assert facts["job_kinds"] == list(JOB_KINDS)
    assert facts["job_states"] == list(JOB_STATES)


def test_quick_facts_failure_taxonomy_is_the_job_managers_and_the_apps(facts):
    # The types the job manager writes: every literal JobError(type=...) under tit/jobs. The
    # contract's JobError.type enum still lists ten values (six never emitted, `forced` and
    # `spawn_error` missing), so it is not the source here.
    emitted = set()
    for path in sorted((REPO / "tit" / "jobs").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            func = getattr(node, "func", None)
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if isinstance(node, ast.Call) and name == "JobError":
                [value] = [k.value for k in node.keywords if k.arg == "type"]
                emitted.add(value.value)
    assert {"runner_failed", "lost"} <= emitted  # the collector found the common ones
    assert set(facts["failure_taxonomy"]) == emitted
    fmt = (REPO / "desktop/src/renderer/app/jobs-rail/format.ts").read_text()
    table = re.search(r"const ERROR_LABEL[^{]*\{(.*?)\};", fmt, re.S).group(1)
    labels = dict(re.findall(r'(\w+): "([^"]+)"', table))
    assert len(labels) == len(emitted)
    assert facts["failure_taxonomy"] == labels
