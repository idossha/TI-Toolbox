"""A ``tools`` job cannot write outside the project through a value attached to a short option.

What this pins
--------------
``tit.jobs.kinds.check_tool_args`` jails every path a ``tools`` job's arguments name to the
manager's project directory (RUN-06). It skipped every token starting with ``-`` unless it had
an ``=`` or was a ``--`` option, so ``-o/tmp/escape.stl`` passed: argparse reads a short
option's value attached to it, and ``tit.tools.nifti_to_mesh`` (``-o``/``--output``) then wrote
there. The oracle for how a token is read is argparse itself, through the tool's real
``main()``: the test records the ``output`` argparse hands to ``nifti_to_mesh`` and checks that
every refused token really is a path outside the project, and every accepted one inside it.

Reproduce: ``.venv/bin/python -m pytest tests/test_tools_arg_jail.py -q``.
Deliberately elsewhere: the module allowlist and the positional-path rule
(``tests/test_jobs_model.py::TestToolsArgumentJail``). Written 2026-10-22 (package p41).
"""

from __future__ import annotations

import argparse
import os
import sys

import pytest

from tit.jobs import kinds
from tit.paths import is_within

MODULE = "tit.tools.nifti_to_mesh"


def _argv(args, project_dir):
    return kinds.command_for(
        "tools",
        {"module": MODULE, "args": args},
        os.path.join(project_dir, "spec.json"),
        project_dir=project_dir,
    )


def _argparse_output(args, monkeypatch) -> str | None:
    """What the tool's own argparse reads as ``--output`` for *args* (the independent oracle)."""
    import tit.tools.nifti_to_mesh as n2m

    seen: dict[str, str | None] = {}

    def _record(input_path, output_path, **_kwargs):
        seen["output"] = output_path
        return {"output_file": output_path, "vertices": 0, "faces": 0}

    monkeypatch.setattr(n2m, "nifti_to_mesh", _record)
    monkeypatch.setattr(n2m, "_report_job_outputs", lambda result: None)
    monkeypatch.setattr(sys, "argv", ["nifti_to_mesh", *args])
    n2m.main()
    return seen["output"]


@pytest.mark.parametrize(
    "args",
    [
        ["seg.nii.gz", "-o/tmp/escape.stl"],
        ["seg.nii.gz", "-o../../etc/x"],
        ["seg.nii.gz", "-vo/tmp/x"],
        ["seg.nii.gz", "-o~/x.stl"],
        ["seg.nii.gz", "-o/tmp/a=b.stl"],  # an "=" must not hide the attached reading
        ["seg.nii.gz", "-o", "/tmp/x"],  # already refused before 2026-10-22
        ["seg.nii.gz", "--output=/tmp/x"],  # already refused before 2026-10-22
    ],
    ids=[
        "attached",
        "attached-traversal",
        "combined-flags",
        "home",
        "equals",
        "split",
        "long",
    ],
)
def test_an_output_outside_the_project_is_refused_however_it_is_spelled(
    args, tmp_path, monkeypatch
):
    project = str(tmp_path / "project")
    os.makedirs(project)
    # argparse reads these tokens as an output path, and that path is outside the project
    # once the tool resolves it against its working directory (the project root).
    output = _argparse_output(args, monkeypatch)
    assert output is not None
    resolved = os.path.join(project, os.path.expanduser(output))
    assert not is_within(project, resolved), output
    with pytest.raises(kinds.KindError, match="outside the project"):
        _argv(args, project)


@pytest.mark.parametrize(
    "spell",
    [
        lambda p: ["seg.nii.gz", "-o" + os.path.join(p, "out.stl")],
        lambda p: ["seg.nii.gz", "-vo" + os.path.join(p, "out.stl")],
        lambda p: ["seg.nii.gz", "-o", os.path.join(p, "out.stl")],
        lambda p: ["seg.nii.gz", "--output=" + os.path.join(p, "out.stl")],
        lambda p: ["seg.nii.gz", "-v", "--clean"],
        lambda p: ["seg.nii.gz", "--clean-threshold", "0.2"],
    ],
    ids=["attached", "combined-flags", "split", "long", "flags", "number"],
)
def test_an_output_inside_the_project_still_runs(spell, tmp_path, monkeypatch):
    project = str(tmp_path / "project")
    os.makedirs(project)
    args = spell(project)
    output = _argparse_output(args, monkeypatch)
    if output is not None:
        assert is_within(project, os.path.join(project, output))
    argv = _argv(args, project)
    assert argv == ["simnibs_python", "-m", MODULE, *args]


def test_an_attached_path_with_no_project_root_is_refused():
    with pytest.raises(kinds.KindError, match="no project directory"):
        kinds.command_for(
            "tools",
            {"module": MODULE, "args": ["seg.nii.gz", "-o/proj/out.stl"]},
            "unused",
            project_dir=None,
        )


def _parser(*flags: str, value: str) -> argparse.ArgumentParser:
    """A tool's argparse with store-true *flags* and one option *value* that takes a path."""
    parser = argparse.ArgumentParser(exit_on_error=False)
    for flag in flags:
        parser.add_argument(flag, dest=f"flag{flag}", action="store_true")
    parser.add_argument(value, dest="path")
    return parser


def test_a_digit_flag_does_not_end_the_run_of_combined_flags(tmp_path):
    """argparse combines digit flags like letters: with ``-v``, ``-1`` and ``-o``, the token
    ``-v1o/tmp/x`` is ``-v -1 -o /tmp/x``. The jail must read past the digit to that ``/tmp/x``
    (``tit.tools`` has no digit flag today; the jail is per token, not per tool)."""
    project = str(tmp_path / "project")
    os.makedirs(project)
    parsed = _parser("-v", "-1", value="-o").parse_args(["-v1o/tmp/x"])
    assert parsed.path == "/tmp/x"
    assert not is_within(project, os.path.join(project, parsed.path))
    with pytest.raises(kinds.KindError, match="outside the project"):
        _argv(["seg.nii.gz", "-v1o/tmp/x"], project)


def test_a_relative_path_attached_to_a_short_option_is_refused_on_purpose(tmp_path):
    """Deliberate false positive. For ``nifti_to_mesh``, ``-oout/x`` is ``--output out/x``,
    inside the project, but the jail does not know which letters a tool's flags are: with
    flags ``-o`` and ``-u`` and an option ``-t``, the same token is ``-o -o -u -t /x``. So every
    reading is checked and this one is refused; write ``-o out/x`` (checked as one path).
    """
    project = str(tmp_path / "project")
    os.makedirs(project)
    parsed = _parser("-o", "-u", value="-t").parse_args(["-oout/x"])
    assert parsed.path == "/x"
    with pytest.raises(kinds.KindError, match="outside the project"):
        _argv(["seg.nii.gz", "-oout/x"], project)
    split = ["seg.nii.gz", "-o", "out/x"]
    assert _argv(split, project) == ["simnibs_python", "-m", MODULE, *split]
