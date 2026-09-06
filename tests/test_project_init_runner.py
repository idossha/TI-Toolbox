"""``simnibs_python -m tit.project_init spec.json`` -- the runner entry point.

What this pins
--------------
The ``project_init`` job kind actually *runs*. Before 2026-09-03 the package had no
``__main__``, so every job of that kind failed at exec with "'tit.project_init' is a package and
cannot be directly executed" (job ``5d0c6180a8004f49`` in Dataset 000). ``tit.jobs.kinds``
guards a kind with ``module_exists()``, which passes for a package with no ``__main__`` -- so
nothing but a real run, or this test, catches it.

Where the numbers come from
---------------------------
None: this is a structural/behavioural test (does the module exist as an executable entry point,
does it scaffold the project, is it idempotent). The scaffolding rules themselves are
``tit.project_init.initializer``'s and are tested there.

Reproduce: ``python3 -m pytest -q tests/test_project_init_runner.py``.

Deliberately elsewhere: what a fresh project directory must contain
(``tests/test_project_init.py``), how the server dispatches kinds (``tests/test_jobs_*.py``).

Written 2026-09-03 (lane S1).
"""

from __future__ import annotations

import importlib.util
import json

import pytest

from tit.jobs import kinds


def test_project_init_has_an_executable_entry_point():
    """The exact gap the failed job hit: the package imports, ``-m`` needs ``__main__``."""
    assert kinds.MODULE_FOR_KIND["project_init"] == "tit.project_init"
    assert importlib.util.find_spec("tit.project_init.__main__") is not None, (
        "tit.project_init has no __main__, so `simnibs_python -m tit.project_init` cannot run"
    )


def test_command_for_builds_the_runner_argv(tmp_path):
    argv = kinds.command_for("project_init", {"example_data": False}, str(tmp_path / "c.json"))
    assert argv[1:3] == ["-m", "tit.project_init"]


def _write_config(tmp_path, **extra) -> str:
    path = tmp_path / "config.json"
    payload = {"project_dir": str(tmp_path / "project"), "example_data": False}
    payload.update(extra)
    (tmp_path / "project").mkdir()
    path.write_text(json.dumps(payload))
    return str(path)


def test_main_scaffolds_the_project_and_exits_zero(tmp_path, capsys):
    from tit.project_init.__main__ import main

    config = _write_config(tmp_path)
    assert main([config]) == 0
    out = capsys.readouterr().out
    assert "Project initialization: Started" in out
    assert (tmp_path / "project" / "sourcedata").is_dir()


def test_main_is_idempotent(tmp_path):
    from tit.project_init.__main__ import main

    config = _write_config(tmp_path)
    assert main([config]) == 0
    assert main([config]) == 0, "re-running project_init on an established project must be a no-op"


@pytest.mark.parametrize(
    "argv, config_patch, expected",
    [([], None, 2), (None, {"project_dir": ""}, 2)],
)
def test_main_refuses_readably_without_its_inputs(tmp_path, capsys, argv, config_patch, expected):
    """A missing argument or project_dir is a message and exit 2, never a traceback."""
    from tit.project_init.__main__ import main

    args = argv if argv is not None else [_write_config(tmp_path, **config_patch)]
    assert main(args) == expected
    err = capsys.readouterr().err
    assert "project_init:" in err and "Traceback" not in err
