"""Job kind -> runner command line (TODO.md §2.3, and the B1 assignment notes).

Every "module" kind runs ``simnibs_python -m <module> <spec_path>`` — the existing
``__main__.py`` contract every runner already implements or will implement (B4). ``tools`` is
different: it doesn't take a spec.json at all, it runs an arbitrary module with explicit args
from the config -- it is therefore allowlisted to ``tit.tools.*``
modules only (ra_14 finding #2): any importable module (``-m http.server``, ``-m pip``, an
attacker's own package on ``PYTHONPATH``) would otherwise be remote code execution for any
token holder, and in the container that's host root via the mounted docker.sock.

The allowlist closes *which module* runs; :data:`TOOL_ARG_POLICY` and :func:`check_tool_args`
close *what it can be told to touch* (RUN-06). Every path-shaped ``config.args`` value must
resolve inside the manager's project root, and the options a tool treats as identifiers
(``--pipeline``, ``--node``) must be safe names -- checked when the argv is built, before the
job is spawned and therefore before any file is created. A ``tools`` job whose args mention a
path but whose manager has no project root bound is refused rather than trusted.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
from pathlib import Path
from typing import Any

PYTHON_INTERPRETER = "simnibs_python"

# The one directory `tools` job modules may resolve into -- sibling of this package (tit/jobs/),
# i.e. tit/tools/. Resolved once at import time; every dotted module name is re-resolved against
# it per call (see _resolve_tool_module_path) rather than trusted from the string alone.
TOOLS_DIR = (Path(__file__).resolve().parent.parent / "tools").resolve()
TOOLS_MODULE_PREFIX = "tit.tools."

MODULE_FOR_KIND: dict[str, str] = {
    "pre": "tit.pre",
    "sim": "tit.sim",
    "flex": "tit.opt.flex",
    "flex_adaptive": "tit.opt.flex",
    "flex_pareto": "tit.opt.flex",
    "ex": "tit.opt.ex",
    "mex": "tit.opt.mex",
    "leadfield": "tit.opt.leadfield_runner",
    "analyzer": "tit.analyzer",
    "stats": "tit.stats",
    "source": "tit.source",
    "blender": "tit.blender",
    "nifti_average": "tit.stats.nifti_average",
    "nilearn": "tit.plotting.nilearn",
    "project_init": "tit.project_init",
    "report": "tit.pre.report",
}

# flex_adaptive/flex_pareto still invoke -m tit.opt.flex; the sub-mode is a config field
# (e.g. {"mode": "adaptive"}) the runner itself dispatches on (tit.opt.flex.drivers, owned by B3).
FLEX_MODE_FOR_KIND: dict[str, str] = {
    "flex": "single",
    "flex_adaptive": "adaptive",
    "flex_pareto": "pareto",
}


class KindError(ValueError):
    """Raised for an unknown kind, or a known kind whose runner module isn't wired up yet."""


def module_exists(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def command_for(
    kind: str,
    config: dict[str, Any],
    spec_path: str,
    *,
    project_dir: str | None = None,
) -> list[str]:
    """The argv to exec for one job. Raises :class:`KindError` for anything it can't build.

    *project_dir* is the root a ``tools`` job's path arguments are jailed to
    (:func:`check_tool_args`); :class:`tit.jobs.manager.JobManager` binds its own.
    """
    config = config or {}

    if kind in MODULE_FOR_KIND:
        module = MODULE_FOR_KIND[kind]
        if not module_exists(module):
            raise KindError(
                f"kind '{kind}' maps to '{module}', which is not importable in this "
                "environment yet (its runner module has not been created — see the "
                "backend change budget in TODO.md §3). This kind cannot run until that "
                "lands."
            )
        return [PYTHON_INTERPRETER, "-m", module, spec_path]

    if kind == "tools":
        module = config.get("module")
        if not module or not isinstance(module, str):
            raise KindError(
                "tools job needs a non-empty config.module (dotted module path)"
            )
        if _resolve_tool_module_path(module) is None:
            raise KindError(
                f"tools job: module {module!r} is not an allowed tit.tools module "
                f"(must be '{TOOLS_MODULE_PREFIX}<name>' and resolve to a file inside "
                f"{TOOLS_DIR})"
            )
        args = _string_list(config.get("args", []))
        check_tool_args(module, args, project_dir)
        return [PYTHON_INTERPRETER, "-m", module, *args]

    raise KindError(f"unknown job kind: {kind!r}")


def _resolve_tool_module_path(module: str) -> Path | None:
    """The on-disk ``.py`` file *module* resolves to, iff it is both dotted under
    ``tit.tools.`` and its import machinery's own resolution actually lands inside
    :data:`TOOLS_DIR` -- ``None`` otherwise (unknown module, not under the prefix, or a name
    that resolves somewhere else entirely). This is the ``tools`` kind's entire attack surface
    (ra_14 finding #2): checking the *string* alone would still let ``config.module`` name any
    other importable dotted path that merely starts with the right prefix in appearance, or a
    package shadowed earlier on ``sys.path``/``PYTHONPATH`` -- resolving through the real import
    system and checking the resulting file's location closes both.
    """
    if not module.startswith(TOOLS_MODULE_PREFIX) or module == TOOLS_MODULE_PREFIX:
        return None
    # A package's own __init__.py is importable under the ordinary dotted-name machinery as
    # "<package>.__init__" (e.g. `importlib.util.find_spec("tit.tools.__init__")` succeeds and
    # resolves inside TOOLS_DIR, same as any real tool module) -- rb_12 re-check NEW issue: this
    # let a "tools" job name it and run tit/tools/__init__.py to (harmless, empty) success. Not a
    # tool script a caller should be able to name, at any depth under the prefix.
    if module.rpartition(".")[2] == "__init__":
        return None
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError, ModuleNotFoundError):
        return None
    if spec is None or not spec.origin:
        return None
    try:
        origin = Path(spec.origin).resolve()
    except OSError:
        return None
    if not origin.is_relative_to(TOOLS_DIR) or not origin.is_file():
        return None
    return origin


#: Per-tool argument policy for the ``tools`` kind: option -> how its value is checked.
#:
#: ``"name"``     a bare identifier that becomes a directory or file component
#: ``"subjects"`` a comma-separated list of subject ids
#: ``"root"``     must be the manager's own project root, not some other directory
#:
#: Anything not listed -- another option's value, or a positional -- is checked by the
#: default rule: if it looks like a path it must resolve inside the project root. That rule
#: is what covers ``tit.tools.electrode_overlay``'s three positional paths, and every tool
#: script added later without a policy entry of its own.
TOOL_ARG_POLICY: dict[str, dict[str, str]] = {
    "tit.tools.pipeline_resolve": {
        "--pipeline": "name",
        "--node": "name",
        "--port": "name",
        "--from-kind": "name",
        "--subjects": "subjects",
        "--project-dir": "root",
    },
}


def _looks_like_a_path(value: str) -> bool:
    """True for anything that could name a filesystem location rather than a plain word."""
    return (
        os.path.isabs(value)
        or value.startswith("~")
        or "/" in value
        or "\\" in value
        or value in (".", "..")
    )


def check_tool_args(module: str, args: list[str], project_dir: str | None) -> None:
    """Raise :class:`KindError` unless every argument of a ``tools`` job stays in bounds.

    RUN-06: ``config.args`` used to be forwarded verbatim, so an allowlisted tool could be
    handed an absolute output path and made to write anywhere the container's user can write.
    """
    from tit.paths import is_valid_subject_id, is_within

    policy = TOOL_ARG_POLICY.get(module, {})

    def check(option: str | None, value: str) -> None:
        rule = policy.get(option or "", "")
        where = option or "argument"
        if rule == "name":
            if not _SAFE_ARG_NAME.match(value):
                raise KindError(
                    f"tools job: {where} {value!r} must be a plain name "
                    f"(letters, digits, '_', '-', '.', at most 64 characters)"
                )
            return
        if rule == "subjects":
            for sid in value.split(","):
                if sid and not is_valid_subject_id(sid):
                    raise KindError(
                        f"tools job: {where} has an invalid subject id {sid!r}"
                    )
            return
        if rule == "root":
            if not project_dir or os.path.realpath(value) != os.path.realpath(
                project_dir
            ):
                raise KindError(
                    f"tools job: {where} must be this server's project directory"
                )
            return
        if not _looks_like_a_path(value):
            return
        if not project_dir:
            raise KindError(
                f"tools job: {where} {value!r} looks like a path, and this manager has no "
                f"project directory to jail it to"
            )
        resolved = os.path.join(project_dir, os.path.expanduser(value))
        if not is_within(project_dir, resolved):
            raise KindError(
                f"tools job: {where} {value!r} resolves outside the project directory"
            )

    pending: str | None = None
    for arg in args:
        if arg.startswith("-") and not os.path.isabs(arg):
            pending = None
            option, sep, inline = arg.partition("=")
            if sep:
                check(option, inline)
            elif option in policy or option.startswith("--"):
                pending = option
            continue
        check(pending, arg)
        pending = None


#: Identifier grammar for a ``"name"`` argument -- a directory or file component a tool builds
#: a path out of. Wider than a subject id only by ``.`` (run names carry versions).
_SAFE_ARG_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        # A single string is treated as a shell-style argument line for convenience.
        return shlex.split(value)
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if value:
        raise KindError(f"config.args must be a list of strings, got {value!r}")
    return []


# -- Docker sibling containers -----------------------------------------------------------------

#: ``tit.pre`` stage flags whose stages spawn sibling containers via Docker-outside-of-Docker:
#: QSIPrep, QSIRecon, DTI tensor extraction and optional FreeSurfer workers.
#: Every other kind
#: (sim, flex, ex, analyzer, stats, tools, ...) is a plain in-container process.
DOCKER_SIBLING_STAGE_FLAGS = (
    "run_qsiprep",
    "run_qsirecon",
    "extract_dti",
    "run_freesurfer",
)


def may_spawn_docker_siblings(kind: str | None, config: Any = None) -> bool:
    """Could a job of this *kind*/*config* have started a sibling Docker container?

    Used to keep cancellation from touching Docker for the overwhelming majority of jobs that
    never could have spawned one -- an unresponsive daemon then cannot delay their cancel.
    Conservative on purpose: a ``pre`` job whose config does not mention any DWI stage flag at
    all (an unrecognised or future shape) is treated as if it might have spawned one.
    """
    if kind != "pre":
        return False
    if not isinstance(config, dict):
        return True
    present = [f for f in DOCKER_SIBLING_STAGE_FLAGS if f in config]
    if not present:
        return True
    return any(bool(config[f]) for f in present)
