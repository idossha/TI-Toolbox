"""Job kind -> runner command line (TODO.md §2.3, and the B1 assignment notes).

Every "module" kind runs ``simnibs_python -m <module> <spec_path>`` — the existing
``__main__.py`` contract every runner already implements or will implement (B4). ``tools`` is
different: it doesn't take a spec.json at all, it runs an arbitrary module with explicit args
from the config -- it is therefore allowlisted to ``tit.tools.*``
modules only (ra_14 finding #2): any importable module (``-m http.server``, ``-m pip``, an
attacker's own package on ``PYTHONPATH``) would otherwise be remote code execution for any
token holder, and in the container that's host root via the mounted docker.sock.

Follow-up not yet done (rb_12 re-check): the allowlist above closes *which module* runs, not
*what it can be told to touch* -- ``config.args`` is forwarded to the chosen ``tit.tools.*``
module verbatim (see ``_string_list`` below), so any positional path argument a tool script
accepts (e.g. an output path) is still fully attacker-controlled and unjailed to the project
directory the way ``routes/viewers.py`` jails viewer paths (ra_14 finding #11). Same trust level
as before this module's fix for path *arguments* specifically -- lower severity now that the
module itself can no longer be arbitrary, but still worth a real jail (e.g. resolve every
path-shaped arg through the same ``resolve_jailed``/``jail_roots`` machinery ``viewspec.py``
already has) before ``tools`` is exposed to anyone less trusted than the desktop app's own token.
"""

from __future__ import annotations

import importlib.util
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


def command_for(kind: str, config: dict[str, Any], spec_path: str) -> list[str]:
    """The argv to exec for one job. Raises :class:`KindError` for anything it can't build."""
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


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        # A single string is treated as a shell-style argument line for convenience.
        return shlex.split(value)
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    if value:
        raise KindError(f"config.args must be a list of strings, got {value!r}")
    return []
